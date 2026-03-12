"""Audit-Domainmodell für die Ingestion-/Index-Pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AuditStage(StrEnum):
    """Standardisierte Pipeline-Stages für Funnel-Analysen."""

    DISCOVER = "discover"
    LOAD = "load"
    TRANSFORM = "transform"
    FILTER = "filter"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"


class AuditStatus(StrEnum):
    """Ergebnisstatus eines Stage-Events."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


class ReasonCode(StrEnum):
    """Initialer Reason-Code-Katalog, erweiterbar für weitere Quellen."""

    FILTERED_BY_RULE = "filtered_by_rule"
    IGNORE_HIDDEN_FILE = "ignore_hidden_file"
    IGNORE_SYSTEM_FILE = "ignore_system_file"
    IGNORE_INDEX_FILE = "ignore_index_file"
    UNCHANGED_INCREMENTAL = "unchanged_incremental"
    EMPTY_DOCUMENT = "empty_document"
    PERMISSION_DENIED = "permission_denied"
    HTTP_TIMEOUT = "http_timeout"
    UNSUPPORTED_MACRO = "unsupported_macro"
    COMPLEX_TABLE = "complex_table"
    TRANSFORM_EXCEPTION = "transform_exception"
    NO_TEXT_AFTER_CLEANUP = "no_text_after_cleanup"
    EMPTY_AFTER_TRANSFORM = "empty_after_transform"
    NO_MEANINGFUL_TEXT = "no_meaningful_text"
    MISSING_SOURCE_CONTENT = "missing_source_content"
    CHUNKING_EXCEPTION = "chunking_exception"
    NO_CHUNKS_CREATED = "no_chunks_created"
    TOO_SMALL_FOR_CHUNKING = "too_small_for_chunking"
    EMBED_EXCEPTION = "embed_exception"
    INDEX_WRITE_EXCEPTION = "index_write_exception"
    BINARY_ONLY = "binary_only"
    ATTACHMENT_ONLY = "attachment_only"
    UNKNOWN_EXCEPTION = "unknown_exception"
    UNCHANGED_SOURCE = "unchanged_source"


@dataclass(slots=True)
class AuditEvent:
    """Ein einzelnes, serialisierbares Audit-Event je Dokument und Stage."""

    run_id: str
    source_type: str
    source_instance: str | None
    stage: str
    status: str | None = None
    document_id: str | None = None
    document_uri: str | None = None
    document_title: str | None = None
    reason_code: str | None = None
    message: str | None = None
    input_count: int | None = None
    output_count: int | None = None
    chunk_count: int | None = None
    duration_ms: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    extra_json: dict[str, Any] | None = None


@dataclass(slots=True)
class PipelineRun:
    """Run-Metadaten für einen Pipeline-Lauf."""

    run_id: str
    started_at: str
    source_type: str
    source_instance: str | None = None
    mode: str | None = None
    status: str = "running"
    finished_at: str | None = None
    total_events: int = 0


def create_run_id(source_type: str, mode: str | None = None) -> str:
    """Erzeugt eine lesbare Run-ID mit Zeitstempel und Quelle."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_suffix = f"_{mode}" if mode else ""
    return f"{timestamp}_{source_type}{mode_suffix}"
