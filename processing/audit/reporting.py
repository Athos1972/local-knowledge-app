"""Aggregationen und Renderer für Audit-Diagnose-Reports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import csv
from pathlib import Path
from typing import Any

from processing.audit.models import AuditStage
from processing.audit.repository import AuditRepository


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
        where_clauses: list[str] = []
        params: list[Any] = []

        if filters.report_date:
            day = filters.report_date.isoformat()
            where_clauses.append("date(started_at) = date(?)")
            params.append(day)
        if filters.run_id:
            where_clauses.append("run_id = ?")
            params.append(filters.run_id)
        if filters.source_type:
            where_clauses.append("source_type = ?")
            params.append(filters.source_type)
        if filters.source_instance:
            where_clauses.append("source_instance = ?")
            params.append(filters.source_instance)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        runs = self.repository.query(f"SELECT * FROM pipeline_runs {where_sql} ORDER BY started_at DESC", tuple(params))
        run_ids = [row["run_id"] for row in runs]
        if not run_ids:
            return {"runs": [], "funnel": {}, "stage_stats": {}, "reason_codes": [], "drop_off": [], "problem_documents": [], "confluence_insights": {}}

        placeholders = ",".join("?" for _ in run_ids)
        events = self.repository.query(
            f"SELECT * FROM document_stage_events WHERE run_id IN ({placeholders}) ORDER BY created_at ASC",
            tuple(run_ids),
        )
        return {
            "runs": [dict(row) for row in runs],
            "funnel": self._build_funnel(events),
            "stage_stats": self._build_stage_stats(events),
            "reason_codes": self._build_reason_codes(events),
            "drop_off": self._build_drop_off(events),
            "problem_documents": self._build_problem_documents(events),
            "confluence_insights": self._build_confluence_insights(events),
            "events": [dict(row) for row in events],
        }

    def _build_funnel(self, events: list[Any]) -> dict[str, dict[str, int]]:
        by_run: dict[str, dict[str, int]] = defaultdict(dict)
        for run_id in {row["run_id"] for row in events}:
            run_events = [e for e in events if e["run_id"] == run_id]
            by_run[run_id] = {
                "discovered": self._count_docs(run_events, AuditStage.DISCOVER),
                "loaded": self._count_docs(run_events, AuditStage.LOAD),
                "transformed": self._count_docs(run_events, AuditStage.TRANSFORM),
                "chunked_docs": self._count_docs(run_events, AuditStage.CHUNK),
                "chunks_created": sum((e["chunk_count"] or 0) for e in run_events if e["stage"] == AuditStage.CHUNK and e["status"] in {"ok", "warning"}),
                "embedded_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.EMBED and e["status"] in {"ok", "warning"}),
                "indexed_chunks": sum((e["output_count"] or 0) for e in run_events if e["stage"] == AuditStage.INDEX and e["status"] in {"ok", "warning"}),
            }
        return by_run

    def _count_docs(self, events: list[Any], stage: str) -> int:
        return len({e["document_id"] for e in events if e["stage"] == stage and e["status"] in {"ok", "warning"} and e["document_id"]})

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

    def _build_drop_off(self, events: list[Any]) -> list[dict[str, Any]]:
        all_drops = []
        for run_id, funnel in self._build_funnel(events).items():
            steps = ["discovered", "loaded", "transformed", "chunked_docs"]
            for prev, nxt in zip(steps, steps[1:]):
                drop = max(0, funnel[prev] - funnel[nxt])
                all_drops.append({"run_id": run_id, "from": prev, "to": nxt, "drop": drop})
        return sorted(all_drops, key=lambda item: item["drop"], reverse=True)

    def _build_problem_documents(self, events: list[Any]) -> list[dict[str, Any]]:
        latest_problem: dict[str, Any] = {}
        for event in events:
            if event["status"] in {"warning", "skipped", "error"} and event["document_id"]:
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

        loaded_docs = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.LOAD and e["status"] == "ok" and e["document_id"]}
        chunk_docs = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.CHUNK and e["status"] in {"ok", "warning"} and e["document_id"]}
        missing_chunk_docs = sorted(loaded_docs - chunk_docs)

        transform_ok = {e["document_id"] for e in conf_events if e["stage"] == AuditStage.TRANSFORM and e["status"] == "ok" and e["document_id"]}
        transform_to_empty = [
            e for e in conf_events if e["document_id"] in transform_ok and e["reason_code"] in {"no_chunks_created", "no_text_after_cleanup"}
        ]

        return {
            "reason_codes_by_instance": {k: dict(v) for k, v in by_instance.items()},
            "loaded_but_not_chunked": missing_chunk_docs,
            "transform_ok_but_empty_afterwards": [dict(e) for e in transform_to_empty],
        }


def render_console(report: dict[str, Any]) -> str:
    lines = []
    lines.append("=== Audit-Report ===")
    lines.append("\nRuns heute:")
    for run in report["runs"]:
        lines.append(f"- {run['run_id']} | {run['started_at']} - {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | {run['status']} | events={run['total_events']}")

    lines.append("\nFunnel pro Run:")
    for run_id, funnel in report["funnel"].items():
        lines.append(f"- {run_id}: {funnel}")

    lines.append("\nStage-Statistiken:")
    for stage, stats in report["stage_stats"].items():
        lines.append(f"- {stage}: ok={stats['ok']} warning={stats['warning']} skipped={stats['skipped']} error={stats['error']}")

    lines.append("\nTop-Reason-Codes:")
    for item in report["reason_codes"][:10]:
        lines.append(f"- {item['reason_code']}: {item['count']}")
        for ex in item["examples"]:
            lines.append(f"  - {ex['document_id']} | {ex['document_title']}")

    if report["drop_off"]:
        top = report["drop_off"][0]
        lines.append(f"\nGrößter Drop-Off: {top['run_id']} {top['from']} -> {top['to']} = {top['drop']}")

    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"# Audit-Report ({now})", "", "## Run-Übersicht"]
    lines.append("| run_id | started_at | finished_at | source_type | source_instance | mode | status | events |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for run in report["runs"]:
        lines.append(f"| {run['run_id']} | {run['started_at']} | {run.get('finished_at') or '-'} | {run['source_type']} | {run.get('source_instance') or '-'} | {run.get('mode') or '-'} | {run['status']} | {run['total_events']} |")
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
