"""Recorder und Kontextmanager für minimal-invasive Audit-Instrumentierung."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from common.logging_setup import get_logger
from processing.audit.models import AuditEvent, AuditStatus, PipelineRun, ReasonCode, create_run_id
from processing.audit.repository import AuditRepository


class StageEventContext(AbstractContextManager["StageEventContext"]):
    """Kontextmanager für ein Stage-Event mit Auto-Status und Fehlererfassung."""

    def __init__(self, recorder: "AuditRecorder", event: AuditEvent):
        self.recorder = recorder
        self.event = event
        self._started = perf_counter()

    def ok(self, message: str | None = None, reason_code: str | None = None) -> None:
        self.event.status = AuditStatus.OK
        self.event.message = message
        self.event.reason_code = reason_code

    def warning(self, reason_code: str, message: str | None = None) -> None:
        self.event.status = AuditStatus.WARNING
        self.event.reason_code = reason_code
        self.event.message = message

    def skipped(self, reason_code: str, message: str | None = None) -> None:
        self.event.status = AuditStatus.SKIPPED
        self.event.reason_code = reason_code
        self.event.message = message

    def error(self, reason_code: str, message: str | None = None) -> None:
        self.event.status = AuditStatus.ERROR
        self.event.reason_code = reason_code
        self.event.message = message

    def __enter__(self) -> "StageEventContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.event.duration_ms = int((perf_counter() - self._started) * 1000)
        if exc is not None:
            self.event.status = AuditStatus.ERROR
            self.event.reason_code = self.event.reason_code or ReasonCode.UNKNOWN_EXCEPTION
            self.event.message = self.event.message or str(exc)

        if self.event.status is None:
            self.event.status = AuditStatus.OK

        self.recorder.record(self.event)
        return False


class AuditRecorder:
    """Schreibt Audit-Events in SQLite und optional als JSONL pro Run."""

    def __init__(self, repository: AuditRepository, jsonl_path: Path | None = None):
        self.repository = repository
        self.jsonl_path = jsonl_path
        self.logger = get_logger("audit")

    def stage(self, *, run_id: str, source_type: str, stage: str, source_instance: str | None = None, document_id: str | None = None, document_uri: str | None = None, document_title: str | None = None, extra_json: dict[str, Any] | None = None) -> StageEventContext:
        event = AuditEvent(
            run_id=run_id,
            source_type=source_type,
            source_instance=source_instance,
            document_id=document_id,
            document_uri=document_uri,
            document_title=document_title,
            stage=stage,
            extra_json=extra_json,
        )
        return StageEventContext(self, event)

    def record(self, event: AuditEvent) -> None:
        self.repository.insert_event(event)
        if self.jsonl_path:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as handle:
                payload = asdict(event)
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.logger.debug(
            "Audit event run_id=%s stage=%s status=%s doc=%s reason=%s",
            event.run_id,
            event.stage,
            event.status,
            event.document_id,
            event.reason_code,
        )


class PipelineRunContext:
    """Verwaltet Lifecycle und Metadaten eines Pipeline-Laufs."""

    def __init__(self, repository: AuditRepository, source_type: str, source_instance: str | None = None, mode: str | None = None, run_id: str | None = None):
        self.repository = repository
        self.run = PipelineRun(
            run_id=run_id or create_run_id(source_type=source_type, mode=mode),
            started_at=datetime.now(UTC).isoformat(),
            source_type=source_type,
            source_instance=source_instance,
            mode=mode,
            status="running",
        )
        self.repository.upsert_run(self.run)

    @property
    def run_id(self) -> str:
        return self.run.run_id

    def finish(self, status: str = "finished") -> None:
        self.run.status = status
        self.run.finished_at = datetime.now(UTC).isoformat()
        self.run.total_events = self.repository.count_events_for_run(self.run_id)
        self.repository.upsert_run(self.run)


def build_audit_components(*, data_root: Path, source_type: str, source_instance: str | None, mode: str | None, run_id: str | None = None, with_jsonl: bool = True) -> tuple[PipelineRunContext, AuditRecorder]:
    """Factory: erstellt RunContext + Recorder aus Standardpfaden."""
    audit_root = data_root / "system" / "audit"
    repository = AuditRepository(audit_root / "pipeline_audit.sqlite")
    run_context = PipelineRunContext(
        repository=repository,
        source_type=source_type,
        source_instance=source_instance,
        mode=mode,
        run_id=run_id,
    )
    jsonl_path = audit_root / "runs" / f"{run_context.run_id}.jsonl" if with_jsonl else None
    recorder = AuditRecorder(repository=repository, jsonl_path=jsonl_path)
    return run_context, recorder
