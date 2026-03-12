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
                "drop_off": [],
                "problem_documents": [],
                "confluence_insights": {},
                "quality": {},
                "events": [],
            }

        events = self._query_events(run_ids)
        funnel = self._build_funnel(events)
        return {
            "runs": [dict(row) for row in runs],
            "funnel": funnel,
            "stage_stats": self._build_stage_stats(events),
            "reason_codes": self._build_reason_codes(events),
            "reason_codes_by_stage": self._build_reason_codes_by_stage(events),
            "drop_off": self._build_drop_off(funnel),
            "problem_documents": self._build_problem_documents(events),
            "confluence_insights": self._build_confluence_insights(events),
            "quality": self._build_quality_metrics(funnel),
            "events": [dict(row) for row in events],
        }

    def build_drilldown(self, filters: ReportFilters) -> list[dict[str, Any]]:
        where_sql, params = self._build_run_where(filters)
        runs = self.repository.query(f"SELECT run_id FROM pipeline_runs {where_sql} ORDER BY started_at DESC", tuple(params))
        run_ids = [row["run_id"] for row in runs]
        if not run_ids:
            return []

        events = self._query_events(run_ids)
        rows: list[dict[str, Any]] = []
        for event in events:
            extra = _parse_extra_json(event["extra_json"])
            warning_flags = _extract_warning_flags(event, extra)
            changed_flag = extra.get("changed_flag")
            if changed_flag is None and event["reason_code"] in {ReasonCode.UNCHANGED_INCREMENTAL, ReasonCode.UNCHANGED_SOURCE}:
                changed_flag = False
            rows.append(
                {
                    "run_id": event["run_id"],
                    "source_type": event["source_type"],
                    "source_name": event["source_instance"],
                    "document_id": event["document_id"],
                    "title": event["document_title"],
                    "stage": event["stage"],
                    "status": event["status"],
                    "reason_code": event["reason_code"],
                    "reason_detail": event["message"],
                    "raw_text_length": event["input_count"],
                    "transformed_text_length": event["output_count"] if event["stage"] == AuditStage.TRANSFORM else None,
                    "chunk_count": event["chunk_count"],
                    "warning_flags": "|".join(warning_flags) if warning_flags else None,
                    "changed_flag": changed_flag,
                    "is_dirty": extra.get("is_dirty"),
                }
            )
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
            f"SELECT * FROM document_stage_events WHERE run_id IN ({placeholders}) ORDER BY created_at ASC",
            tuple(run_ids),
        )

    def _build_funnel(self, events: list[Any]) -> dict[str, dict[str, int]]:
        by_run: dict[str, dict[str, int]] = {}
        for run_id in {row["run_id"] for row in events}:
            run_events = [e for e in events if e["run_id"] == run_id]
            unchanged = self._count_docs_by_reason(run_events, AuditStage.FILTER, AuditStatus.SKIPPED, UNCHANGE_REASONS)
            filtered = self._count_docs_by_reason(run_events, AuditStage.FILTER, AuditStatus.SKIPPED, None) - unchanged
            transformed_ok = self._count_docs(run_events, AuditStage.TRANSFORM, {AuditStatus.OK, AuditStatus.WARNING})
            by_run[run_id] = {
                "discovered": self._count_docs(run_events, AuditStage.DISCOVER, {AuditStatus.OK, AuditStatus.WARNING}),
                "loaded": self._count_docs(run_events, AuditStage.LOAD, {AuditStatus.OK, AuditStatus.WARNING}),
                "unchanged_skipped": max(0, unchanged),
                "filtered_skipped": max(0, filtered),
                "transform_failed": self._count_docs(run_events, AuditStage.TRANSFORM, {AuditStatus.ERROR}),
                "transformed_ok": transformed_ok,
                "transformed": transformed_ok,
                "chunked_docs": self._count_docs(run_events, AuditStage.CHUNK, {AuditStatus.OK, AuditStatus.WARNING}),
                "chunks_created": sum((e["chunk_count"] or 0) for e in run_events if e["stage"] == AuditStage.CHUNK and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
                "embedded_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.EMBED and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
                "indexed_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.INDEX and e["status"] in {AuditStatus.OK, AuditStatus.WARNING}),
            }
        return by_run

    def _count_docs(self, events: list[Any], stage: str, statuses: set[str]) -> int:
        return len({e["document_id"] for e in events if e["stage"] == stage and e["status"] in statuses and e["document_id"]})

    def _count_docs_by_reason(self, events: list[Any], stage: str, status: str, reasons: set[str] | None) -> int:
        return len(
            {
                e["document_id"]
                for e in events
                if e["stage"] == stage
                and e["status"] == status
                and e["document_id"]
                and (reasons is None or e["reason_code"] in reasons)
            }
        )

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

    def _build_drop_off(self, funnel: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        all_drops = []
        for run_id, values in funnel.items():
            candidate_for_transform = max(0, values["loaded"] - values["unchanged_skipped"])
            transitions = [
                ("loaded", "candidate_for_transform", values["loaded"], candidate_for_transform),
                ("candidate_for_transform", "transformed_ok", candidate_for_transform, values["transformed_ok"]),
                ("transformed_ok", "chunked_docs", values["transformed_ok"], values["chunked_docs"]),
            ]
            for prev_name, nxt_name, prev_count, nxt_count in transitions:
                all_drops.append({"run_id": run_id, "from": prev_name, "to": nxt_name, "drop": max(0, prev_count - nxt_count)})
        return sorted(all_drops, key=lambda item: item["drop"], reverse=True)

    def _build_quality_metrics(self, funnel: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int | str]]:
        quality: dict[str, dict[str, float | int | str]] = {}
        for run_id, values in funnel.items():
            loaded = values["loaded"]
            transformed_ok = values["transformed_ok"]
            transformed_base = max(1, loaded)
            chunk_base = max(1, transformed_ok)
            chunks_created = values["chunks_created"]
            quality[run_id] = {
                "transform_quote": transformed_ok / transformed_base,
                "chunk_quote": values["chunked_docs"] / chunk_base,
                "index_quote": values["indexed_chunks"] / max(1, chunks_created),
                "largest_loss_semantic": "loaded->candidate_for_transform" if values["unchanged_skipped"] >= values["filtered_skipped"] + values["transform_failed"] else "candidate_for_transform->transformed_ok",
                "candidate_for_transform": max(0, loaded - values["unchanged_skipped"]),
            }
        return quality

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


def render_console(report: dict[str, Any]) -> str:
    lines = ["=== Audit-Report ===", "", "Runs:"]
    for run in report["runs"]:
        lines.append(
            f"- {run['run_id']} | {run['started_at']} - {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | {run['status']} | events={run['total_events']}"
        )

    lines.append("\nFunnel pro Run:")
    for run_id, funnel in report["funnel"].items():
        quality = report["quality"].get(run_id, {})
        lines.append(f"- {run_id}: {funnel}")
        lines.append(
            "  Transform-Quote={:.1%} | Chunk-Quote={:.1%} | Index-Quote={:.1%} | candidate_for_transform={}".format(
                quality.get("transform_quote", 0.0),
                quality.get("chunk_quote", 0.0),
                quality.get("index_quote", 0.0),
                quality.get("candidate_for_transform", 0),
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

    if report["drop_off"]:
        top = report["drop_off"][0]
        lines.append(f"\nGrößter Drop-Off: {top['run_id']} {top['from']} -> {top['to']} = {top['drop']}")

    worst = sorted(
        (
            {
                "run_id": run_id,
                "transform_quote": metrics.get("transform_quote", 0.0),
            }
            for run_id, metrics in report["quality"].items()
        ),
        key=lambda item: item["transform_quote"],
    )
    if worst:
        lines.append("\nRuns mit niedrigster Transform-Quote:")
        for row in worst[:5]:
            lines.append(f"- {row['run_id']}: {row['transform_quote']:.1%}")

    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"# Audit-Report ({now})", "", "## Run-Übersicht"]
    lines.append("| run_id | started_at | finished_at | source_type | source_instance | mode | status | events |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for run in report["runs"]:
        lines.append(
            f"| {run['run_id']} | {run['started_at']} | {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | {run['status']} | {run['total_events']} |"
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
            "raw_text_length",
            "transformed_text_length",
            "chunk_count",
            "warning_flags",
            "changed_flag",
            "is_dirty",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_drilldown_json(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
