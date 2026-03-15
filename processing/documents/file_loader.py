"""Recursive file loader for local document exports and attachment sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from processing.documents.reference_resolver import resolve_document_reference
from sources.document import stable_hash
from transformers.markitdown_transformer import MarkItDownTransformer


@dataclass(slots=True)
class DocumentFile:
    """Describes one supported source document file."""

    source_path: Path
    relative_path: Path
    routing_path: Path
    source_origin: str
    source_system: str
    source_collection: str
    source_path_value: str
    document_id: str


@dataclass(slots=True)
class DocumentSource:
    """One discovery root plus origin-specific path interpretation."""

    origin: str
    root_path: Path


class DocumentFileLoader:
    """Loads supported local files from multiple export trees."""

    def __init__(self, input_root: Path | None = None, transformer: MarkItDownTransformer | None = None, sources: list[DocumentSource] | None = None):
        self.transformer = transformer or MarkItDownTransformer()
        resolved_sources = list(sources or [])
        if input_root is not None:
            resolved_sources.insert(0, DocumentSource(origin="documents", root_path=input_root))
        self.sources = [
            DocumentSource(origin=source.origin, root_path=source.root_path.expanduser().resolve())
            for source in resolved_sources
        ]

    def load_documents(self) -> Iterable[DocumentFile]:
        """Yield all recursively discovered files supported by the transformer."""
        for source in self.sources:
            if not source.root_path.exists():
                continue

            for path in sorted(source.root_path.rglob("*")):
                if not path.is_file():
                    continue
                if not self.transformer.can_handle(path):
                    continue

                document = self._build_document(source, path)
                if document is None:
                    continue
                yield document

    def _build_document(self, source: DocumentSource, path: Path) -> DocumentFile | None:
        relative_path = path.relative_to(source.root_path)
        reference = resolve_document_reference(path)
        if reference is None:
            return None

        source_path_value = str(path)
        document_id = stable_hash(reference.routing_path.as_posix().lower())
        return DocumentFile(
            source_path=path,
            relative_path=relative_path,
            routing_path=reference.routing_path,
            source_origin=reference.source_origin,
            source_system=reference.source_system,
            source_collection=reference.source_collection,
            source_path_value=source_path_value,
            document_id=document_id,
        )
