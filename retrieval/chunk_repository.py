from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from common.logging_setup import AppLogger

logger = AppLogger.get_logger()


@dataclass(slots=True)
class ChunkRecord:
    """Interne Repräsentation eines geladenen Chunks inkl. Dokument-Metadaten."""

    doc_id: str
    chunk_id: str
    title: str
    text: str
    metadata: dict[str, Any]
    source_ref: str | None = None


class ChunkRepository:
    """Lädt Chunk-JSONL-Dateien und optionale Dokument-Metadaten vom Dateisystem."""

    def __init__(self, data_root: Path | None = None, max_logged_errors: int = 5):
        self.data_root = (data_root or (Path.home() / "local-knowledge-data")).expanduser().resolve()
        self.chunks_dir = self.data_root / "processed" / "chunks"
        self.metadata_dir = self.data_root / "processed" / "metadata"
        self.max_logged_errors = max(1, max_logged_errors)
        self._metadata_cache: dict[str, dict[str, Any]] = {}

    def load_chunks(self) -> list[ChunkRecord]:
        """Lädt alle Chunks aus `processed/chunks/*.jsonl` robust und fehlertolerant."""
        if not self.chunks_dir.exists():
            logger.warning("Chunks directory not found: %s", self.chunks_dir)
            return []

        records: list[ChunkRecord] = []
        logged_errors = 0
        total_errors = 0

        for chunk_file in sorted(self.chunks_dir.glob("*.jsonl")):
            file_records, file_errors = self._load_chunk_file(chunk_file)
            records.extend(file_records)
            total_errors += file_errors

            if file_errors > 0 and logged_errors < self.max_logged_errors:
                logger.warning("Encountered %s parse errors in chunk file: %s", file_errors, chunk_file)
                logged_errors += 1

        if total_errors > 0:
            logger.warning("Chunk loading completed with %s parse errors.", total_errors)

        logger.info("Loaded %s chunks from %s", len(records), self.chunks_dir)
        return records

    def _load_chunk_file(self, path: Path) -> tuple[list[ChunkRecord], int]:
        records: list[ChunkRecord] = []
        errors = 0

        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue

                    try:
                        data = json.loads(stripped)
                    except json.JSONDecodeError:
                        errors += 1
                        continue

                    record = self._build_record(data)
                    if record is None:
                        errors += 1
                        continue
                    records.append(record)
        except OSError as exc:
            logger.warning("Could not read chunk file %s: %s", path, exc)
            return [], 1

        return records, errors

    def _build_record(self, chunk_data: dict[str, Any]) -> ChunkRecord | None:
        doc_id = self._as_non_empty_str(chunk_data.get("doc_id"))
        chunk_id = self._as_non_empty_str(chunk_data.get("chunk_id"))
        title = self._as_non_empty_str(chunk_data.get("title"))
        text = self._as_non_empty_str(chunk_data.get("text"))

        if not doc_id or not chunk_id or not text:
            return None

        metadata = chunk_data.get("metadata")
        merged_metadata: dict[str, Any] = metadata if isinstance(metadata, dict) else {}

        document_metadata = self._load_document_metadata(doc_id)
        if document_metadata:
            merged_metadata = {**document_metadata, **merged_metadata}

        source_ref = self._extract_source_ref(document_metadata)

        return ChunkRecord(
            doc_id=doc_id,
            chunk_id=chunk_id,
            title=title or doc_id,
            text=text,
            metadata=merged_metadata,
            source_ref=source_ref,
        )

    def _load_document_metadata(self, doc_id: str) -> dict[str, Any]:
        if doc_id in self._metadata_cache:
            return self._metadata_cache[doc_id]

        path = self.metadata_dir / f"{doc_id}.json"
        if not path.exists():
            self._metadata_cache[doc_id] = {}
            return {}

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict):
                    self._metadata_cache[doc_id] = data
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load metadata for doc_id=%s: %s", doc_id, exc)

        self._metadata_cache[doc_id] = {}
        return {}

    @staticmethod
    def _extract_source_ref(metadata: dict[str, Any]) -> str | None:
        source = metadata.get("source")
        if not isinstance(source, dict):
            return None

        source_ref = source.get("source_ref")
        if isinstance(source_ref, str) and source_ref.strip():
            return source_ref
        return None

    @staticmethod
    def _as_non_empty_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""
