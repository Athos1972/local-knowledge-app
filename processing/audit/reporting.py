"""Aggregationen und Renderer für Audit-Diagnose-Reports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import csv
import json
from pathlib import Path
from typing import Any

from processing.audit.models import AuditStage, AuditStatus, ReasonCode
from processing.audit.repository import AuditRepository

UNCHANGE_REASONS = {ReasonCode.UNCHANGED_INCREMENTAL, ReasonCode.UNCHANGED_SOURCE}


@dataclass(slots=True)
class ReportFilters:
    report_date: date | None = None
    run_id: str | None = None
    source_type: str | None = None
    source_instance: str | None = None
    only_problematic: bool = False


class AuditReportService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def build_report(self, filters: ReportFilters) -> dict[str, Any]:
        where_sql, params = self._build_run_where(filters)
        runs = self.repository.query(f"SELECT * FROM pipeline_runs {where_sql} ORDER BY started_at DESC", tuple(params))
        run_ids = [row["run_id"] for row in runs]
        if not run_ids:
            return {
                "runs": [],
                "funnel": {},
                "stage_stats": {},
                "reason_codes": [],
                "reason_codes_by_stage": {},
                "reason_codes_by_run": {},
                "drop_off": [],
                "problem_documents": [],
                "confluence_insights": {},
                "quality": {},
                "events": [],
            }

        events = self._query_events(run_ids)
        run_types = self._classify_run_types(runs, events)
        funnel = self._build_funnel(events)
        return {
            "runs": [self._enrich_run(dict(row), run_types.get(row["run_id"], "mixed")) for row in runs],
            "funnel": funnel,
            "stage_stats": self._build_stage_stats(events),
            "reason_codes": self._build_reason_codes(events),
            "reason_codes_by_stage": self._build_reason_codes_by_stage(events),
            "reason_codes_by_run": self._build_reason_codes_by_run(events),
            "drop_off": self._build_drop_off(funnel),
            "problem_documents": self._build_problem_documents(events),
            "confluence_insights": self._build_confluence_insights(events),
            "quality": self._build_quality_metrics(funnel, run_types),
            "events": [dict(row) for row in events],
            "run_types": run_types,
        }

    def build_drilldown(self, filters: ReportFilters) -> list[dict[str, Any]]:
        where_sql, params = self._build_run_where(filters)
        runs = self.repository.query(f"SELECT run_id FROM pipeline_runs {where_sql} ORDER BY started_at DESC", tuple(params))
        run_ids = [row["run_id"] for row in runs]
        if not run_ids:
            return []

        events = self._query_events(run_ids)
        rows: list[dict[str, Any]] = []
        by_doc: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for event in events:
            if not event["document_id"]:
                continue
            by_doc[(event["run_id"], event["document_id"])].append(event)

        for (run_id, document_id), doc_events in sorted(by_doc.items()):
            latest = doc_events[-1]
            source_type = latest["source_type"]
            extra_items = [_parse_extra_json(evt["extra_json"]) for evt in doc_events]
            warning_flags = sorted({flag for evt, extra in zip(doc_events, extra_items, strict=False) for flag in _extract_warning_flags(evt, extra)})
            changed_flag = _resolve_changed_flag(doc_events, extra_items)
            raw_text_length = _last_metric(doc_events, "input_count")
            transformed_text_length = _last_transform_output(doc_events)
            chunk_count = _last_metric(doc_events, "chunk_count")
            is_problematic = _is_problematic_event(latest, changed_flag)
            if filters.only_problematic and not is_problematic:
                continue

            rows.append(
                {
                    "run_id": run_id,
                    "source_type": source_type,
                    "source_name": latest["source_instance"],
                    "document_id": document_id,
                    "title": latest["document_title"],
                    "stage": latest["stage"],
                    "status": latest["status"],
                    "reason_code": latest["reason_code"],
                    "reason_detail": latest["message"],
                    "changed_flag": changed_flag,
                    "is_dirty": _last_extra(extra_items, "is_dirty"),
                    "unchanged_flag": changed_flag is False,
                    "raw_text_length": raw_text_length,
                    "transformed_text_length": transformed_text_length,
                    "chunk_count": chunk_count,
                    "warning_flags": "|".join(warning_flags) if warning_flags else None,
                    "is_problematic": is_problematic,
                    "source_path": latest["document_uri"],
                    "file_path": latest["document_uri"] if source_type in {"filesystem", "anythingllm_ingest"} else None,
                    "page_id": document_id if source_type == "confluence" else None,
                    "content_id": _last_extra(extra_items, "content_id"),
                }
            )
        rows.sort(key=lambda row: (not row["is_problematic"], row["status"] == AuditStatus.OK, row["run_id"], row["document_id"]))
        return rows

    def _build_run_where(self, filters: ReportFilters) -> tuple[str, list[Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []
        if filters.report_date:
            where_clauses.append("date(started_at) = date(?)")
            params.append(filters.report_date.isoformat())
        if filters.run_id:
            where_clauses.append("run_id = ?")
            params.append(filters.run_id)
        if filters.source_type:
            where_clauses.append("source_type = ?")
            params.append(filters.source_type)
        if filters.source_instance:
            where_clauses.append("source_instance = ?")
            params.append(filters.source_instance)
        return (f"WHERE {' AND '.join(where_clauses)}" if where_clauses else "", params)

    def _query_events(self, run_ids: list[str]) -> list[Any]:
        placeholders = ",".join("?" for _ in run_ids)
        return self.repository.query(
            f"SELECT * FROM document_stage_events WHERE run_id IN ({placeholders}) ORDER BY created_at ASC, id ASC",
            tuple(run_ids),
        )

    def _build_funnel(self, events: list[Any]) -> dict[str, dict[str, int]]:
        by_run: dict[str, dict[str, int]] = {}
        for run_id in {row["run_id"] for row in events}:
            run_events = [e for e in events if e["run_id"] == run_id]
            unchanged_docs = self._find_unchanged_docs(run_events)
            filter_skipped_docs = self._find_filter_skipped_docs(run_events)
            loaded_count = self._count_docs(run_events, AuditStage.LOAD, {AuditStatus.OK, AuditStatus.WARNING})
            transformed_ok = self._count_docs(run_events, AuditStage.TRANSFORM, {AuditStatus.OK, AuditStatus.WARNING})
            candidate_for_transform = max(0, loaded_count - len(unchanged_docs))
            by_run[run_id] = {
                "discovered": self._count_docs(run_events, AuditStage.DISCOVER, {AuditStatus.OK, AuditStatus.WARNING}),
                "loaded": loaded_count,
                "unchanged_skipped": len(unchanged_docs),
                "filtered_skipped": len(filter_skipped_docs - unchanged_docs),
                "transform_failed": self._count_docs(run_events, AuditStage.TRANSFORM, {AuditStatus.ERROR}),
                "transformed_ok": transformed_ok,
                "transformed": transformed_ok,
                "candidate_for_transform": candidate_for_transform,
                "expected_dropoff": max(0, loaded_count - candidate_for_transform),
                "problematic_dropoff": max(0, candidate_for_transform - transformed_ok),
                "chunked_docs": self._count_docs(run_events, AuditStage.CHUNK, {AuditStatus.OK, AuditStatus.WARNING}),
                "chunks_created": sum((e["chunk_count"] or 0) for e in run_events if e["stage"] == AuditStage.CHUNK and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
                "embedded_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.EMBED and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
                "indexed_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.INDEX and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
            }
        return by_run

    def _find_filter_skipped_docs(self, events: list[Any]) -> set[str]:
        return {
            e["document_id"]
            for e in events
            if e["stage"] == AuditStage.FILTER and e["status"] == AuditStatus.SKIPPED and e["document_id"]
        }

    def _find_unchanged_docs(self, events: list[Any]) -> set[str]:
        unchanged: set[str] = set()
        for event in events:
            if event["stage"] != AuditStage.FILTER or event["status"] != AuditStatus.SKIPPED or not event["document_id"]:
                continue
            extra = _parse_extra_json(event["extra_json"])
            changed_flag = extra.get("changed_flag")
            if event["reason_code"] in UNCHANGE_REASONS or (changed_flag is False and not event["reason_code"]):
                unchanged.add(event["document_id"])
        return unchanged

    def _count_docs(self, events: list[Any], stage: str, statuses: set[str]) -> int:
        return len({e["document_id"] for e in events if e["stage"] == stage and e["status"] in statuses and e["document_id"]})

    def _build_stage_stats(self, events: list[Any]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "warning": 0, "skipped": 0, "error": 0})
        for event in events:
            stats[event["stage"]][event["status"]] += 1
        return dict(stats)

    def _build_reason_codes(self, events: list[Any]) -> list[dict[str, Any]]:
        grouped: dict[str, list[Any]] = defaultdict(list)
        for event in events:
            if event["reason_code"]:
                grouped[event["reason_code"]].append(event)
        items = []
        for reason, reason_events in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
            examples = []
            seen = set()
            for event in reason_events:
                key = (event["document_id"], event["document_title"])
                if key in seen:
                    continue
                seen.add(key)
                examples.append({"document_id": event["document_id"], "document_title": event["document_title"]})
                if len(examples) >= 5:
                    break
            items.append({"reason_code": reason, "count": len(reason_events), "examples": examples})
        return items

    def _build_reason_codes_by_stage(self, events: list[Any]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for event in events:
            if event["reason_code"]:
                grouped[event["stage"]][event["reason_code"]] += 1
        result: dict[str, list[dict[str, Any]]] = {}
        for stage, rows in grouped.items():
            result[stage] = [
                {"reason_code": reason_code, "count": count}
                for reason_code, count in sorted(rows.items(), key=lambda item: item[1], reverse=True)
            ]
        return result

    def _build_reason_codes_by_run(self, events: list[Any]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for event in events:
            if event["reason_code"]:
                grouped[event["run_id"]][event["reason_code"]] += 1
        return {
            run_id: [
                {"reason_code": reason_code, "count": count}
                for reason_code, count in sorted(rows.items(), key=lambda item: item[1], reverse=True)
            ]
            for run_id, rows in grouped.items()
        }

    def _build_drop_off(self, funnel: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        all_drops = []
        for run_id, values in funnel.items():
            candidate_for_transform = values["candidate_for_transform"]
            transitions = [
                ("loaded", "candidate_for_transform", values["loaded"], candidate_for_transform),
                ("candidate_for_transform", "transformed_ok", candidate_for_transform, values["transformed_ok"]),
                ("transformed_ok", "chunked_docs", values["transformed_ok"], values["chunked_docs"]),
            ]
            for prev_name, nxt_name, prev_count, nxt_count in transitions:
                all_drops.append({"run_id": run_id, "from": prev_name, "to": nxt_name, "drop": max(0, prev_count - nxt_count)})
        return sorted(all_drops, key=lambda item: item["drop"], reverse=True)

    def _classify_run_types(self, runs: list[Any], events: list[Any]) -> dict[str, str]:
        events_by_run: dict[str, set[str]] = defaultdict(set)
        for event in events:
            events_by_run[event["run_id"]].add(event["stage"])

        run_types: dict[str, str] = {}
        for run in runs:
            run_id = run["run_id"]
            stages = events_by_run.get(run_id, set())
            source_type = run["source_type"]
            if source_type == "anythingllm_ingest":
                run_type = "ingest"
            elif AuditStage.INDEX in stages and AuditStage.TRANSFORM not in stages:
                run_type = "index"
            elif AuditStage.EMBED in stages and AuditStage.TRANSFORM not in stages and AuditStage.INDEX not in stages:
                run_type = "ingest"
            elif AuditStage.TRANSFORM in stages:
                run_type = "transform"
            elif AuditStage.CHUNK in stages:
                run_type = "chunk"
            else:
                run_type = "mixed"
            run_types[run_id] = run_type
        return run_types

    def _build_quality_metrics(self, funnel: dict[str, dict[str, int]], run_types: dict[str, str]) -> dict[str, dict[str, float | int | str | None]]:
        quality: dict[str, dict[str, float | int | str | None]] = {}
        for run_id, values in funnel.items():
            loaded = values["loaded"]
            transformed_ok = values["transformed_ok"]
            chunks_created = values["chunks_created"]
            run_type = run_types.get(run_id, "mixed")
            metrics: dict[str, float | int | str | None] = {
                "run_type": run_type,
                "largest_loss_semantic": "loaded->candidate_for_transform" if values["unchanged_skipped"] >= values["filtered_skipped"] + values["transform_failed"] else "candidate_for_transform->transformed_ok",
                "candidate_for_transform": values["candidate_for_transform"],
                "expected_dropoff": values["expected_dropoff"],
                "problematic_dropoff": values["problematic_dropoff"],
                "transform_quote": None,
                "chunk_quote": None,
                "index_quote": None,
            }
            if run_type in {"transform", "chunk", "mixed"}:
                metrics["transform_quote"] = transformed_ok / max(1, loaded)
                metrics["chunk_quote"] = values["chunked_docs"] / max(1, transformed_ok)
            if run_type in {"index", "mixed"} and chunks_created > 0:
                metrics["index_quote"] = values["indexed_chunks"] / chunks_created
            quality[run_id] = metrics
        return quality

    def _enrich_run(self, run: dict[str, Any], run_type: str) -> dict[str, Any]:
        run["run_type"] = run_type
        return run

    def _build_problem_documents(self, events: list[Any]) -> list[dict[str, Any]]:
        latest_problem: dict[str, Any] = {}
        for event in events:
            if event["status"] in {AuditStatus.WARNING, AuditStatus.SKIPPED, AuditStatus.ERROR} and event["document_id"]:
                latest_problem[event["document_id"]] = event
        return [
            {
                "document_id": value["document_id"],
                "title": value["document_title"],
                "stage": value["stage"],
                "status": value["status"],
                "reason_code": value["reason_code"],
                "message": value["message"],
            }
            for value in latest_problem.values()
        ]

    def _build_confluence_insights(self, events: list[Any]) -> dict[str, Any]:
        conf_events = [e for e in events if e["source_type"] == "confluence"]
        if not conf_events:
            return {}

        by_instance: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for event in conf_events:
            instance = event["source_instance"] or "unknown"
            if event["reason_code"]:
                by_instance[instance][event["reason_code"]] += 1

        loaded_docs = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.LOAD and e["status"] == AuditStatus.OK and e["document_id"]}
        chunk_docs = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.CHUNK and e["status"] in {AuditStatus.OK, AuditStatus.WARNING} and e["document_id"]}
        missing_chunk_docs = sorted(loaded_docs - chunk_docs)

        transform_ok = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.TRANSFORM and e["status"] == AuditStatus.OK and e["document_id"]}
        transform_to_empty = [
            e
            for e in conf_events
            if e["document_id"] in transform_ok and e["reason_code"] in {ReasonCode.NO_CHUNKS_CREATED, ReasonCode.NO_TEXT_AFTER_CLEANUP, ReasonCode.EMPTY_AFTER_TRANSFORM}
        ]

        return {
            "reason_codes_by_instance": {k: dict(v) for k, v in by_instance.items()},
            "loaded_but_not_chunked": missing_chunk_docs,
            "transform_ok_but_empty_afterwards": [dict(e) for e in transform_to_empty],
        }


def _parse_extra_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_warning_flags(event: Any, extra_json: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    raw_flags = extra_json.get("warning_flags")
    if isinstance(raw_flags, list):
        flags.extend(str(item) for item in raw_flags)
    reason_code = event["reason_code"] if "reason_code" in event.keys() else None
    if reason_code in {ReasonCode.UNSUPPORTED_MACRO, ReasonCode.COMPLEX_TABLE}:
        flags.append(str(reason_code))
    return sorted(set(flags))


def _resolve_changed_flag(events: list[Any], extras: list[dict[str, Any]]) -> bool | None:
    for extra in reversed(extras):
        if "changed_flag" in extra:
            return extra["changed_flag"]
    for event in reversed(events):
        if event["reason_code"] in UNCHANGE_REASONS:
            return False
    return None


def _last_metric(events: list[Any], key: str) -> int | None:
    for event in reversed(events):
        value = event[key]
        if value is not None:
            return value
    return None


def _last_transform_output(events: list[Any]) -> int | None:
    for event in reversed(events):
        if event["stage"] == AuditStage.TRANSFORM and event["output_count"] is not None:
            return event["output_count"]
    return None


def _last_extra(extras: list[dict[str, Any]], key: str) -> Any:
    for extra in reversed(extras):
        if key in extra:
            return extra[key]
    return None


def _fmt_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _is_problematic_event(event: Any, changed_flag: bool | None) -> bool:
    if event["status"] in {AuditStatus.WARNING, AuditStatus.ERROR}:
        return True
    if event["status"] == AuditStatus.SKIPPED:
        if event["reason_code"] in UNCHANGE_REASONS:
            return False
        if changed_flag is False and not event["reason_code"]:
            return False
        return True
    return False


def render_console(report: dict[str, Any]) -> str:
    lines = ["=== Audit-Report ===", "", "Runs:"]
    for run in report["runs"]:
        lines.append(
            f"- {run['run_id']} | {run['started_at']} - {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | type={run.get('run_type', 'mixed')} | {run['status']} | events={run['total_events']}"
        )

    lines.append("\nFunnel pro Run:")
    for run_id, funnel in report["funnel"].items():
        quality = report["quality"].get(run_id, {})
        lines.append(f"- {run_id}: {funnel}")
        lines.append(
            "  run_type={} | Transform-Quote={} | Chunk-Quote={} | Index-Quote={} | candidate_for_transform={} | expected_dropoff={} | problematic_dropoff={}".format(
                quality.get("run_type", "mixed"),
                _fmt_percent(quality.get("transform_quote")),
                _fmt_percent(quality.get("chunk_quote")),
                _fmt_percent(quality.get("index_quote")),
                quality.get("candidate_for_transform", 0),
                quality.get("expected_dropoff", 0),
                quality.get("problematic_dropoff", 0),
            )
        )

    lines.append("\nStage-Statistiken:")
    for stage, stats in report["stage_stats"].items():
        lines.append(f"- {stage}: ok={stats['ok']} warning={stats['warning']} skipped={stats['skipped']} error={stats['error']}")

    lines.append("\nTop-Reason-Codes (gesamt):")
    for item in report["reason_codes"][:10]:
        lines.append(f"- {item['reason_code']}: {item['count']}")

    lines.append("\nTop-Reason-Codes je Stage:")
    for stage, items in report["reason_codes_by_stage"].items():
        top = ", ".join(f"{row['reason_code']}={row['count']}" for row in items[:5])
        lines.append(f"- {stage}: {top or '-'}")

    if report.get("reason_codes_by_run"):
        lines.append("\nTop-Reason-Codes je Run:")
        for run_id, items in report["reason_codes_by_run"].items():
            top = ", ".join(f"{row['reason_code']}={row['count']}" for row in items[:5])
            lines.append(f"- {run_id}: {top or '-'}")

    largest_expected = max(
        ({"run_id": run_id, "drop": values["expected_dropoff"]} for run_id, values in report["funnel"].items()),
        key=lambda item: item["drop"],
        default=None,
    )
    largest_problematic = max(
        ({"run_id": run_id, "drop": values["problematic_dropoff"]} for run_id, values in report["funnel"].items()),
        key=lambda item: item["drop"],
        default=None,
    )
    if largest_expected:
        lines.append(f"\nGrößter erwarteter Drop-Off (loaded -> candidate_for_transform): {largest_expected['run_id']} = {largest_expected['drop']}")
    if largest_problematic:
        lines.append(f"Größter problematischer Drop-Off (candidate_for_transform -> transformed_ok): {largest_problematic['run_id']} = {largest_problematic['drop']}")

    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"# Audit-Report ({now})", "", "## Run-Übersicht"]
    lines.append("| run_id | started_at | finished_at | source_type | source_instance | mode | run_type | status | events |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for run in report["runs"]:
        lines.append(
            f"| {run['run_id']} | {run['started_at']} | {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | {run.get('run_type', 'mixed')} | {run['status']} | {run['total_events']} |"
        )
    lines.append("\n## Funnel pro Run")
    for run_id, funnel in report["funnel"].items():
        lines.append(f"- **{run_id}**: {funnel}")
    lines.append("\n## Top-Reason-Codes")
    for item in report["reason_codes"][:10]:
        lines.append(f"- **{item['reason_code']}**: {item['count']}")
    return "\n".join(lines)


def export_problem_documents_csv(report: dict[str, Any], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document_id", "title", "stage", "status", "reason_code", "message"])
        writer.writeheader()
        writer.writerows(report["problem_documents"])


def export_drilldown_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "run_id",
            "source_type",
            "source_name",
            "document_id",
            "title",
            "stage",
            "status",
            "reason_code",
            "reason_detail",
            "changed_flag",
            "is_dirty",
            "unchanged_flag",
            "raw_text_length",
            "transformed_text_length",
            "chunk_count",
            "warning_flags",
            "is_problematic",
            "source_path",
            "file_path",
            "page_id",
            "content_id",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_drilldown_json(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
