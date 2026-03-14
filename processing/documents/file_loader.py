"""Recursive file loader for local document exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sources.document import stable_hash
from transformers.markitdown_transformer import MarkItDownTransformer


@dataclass(slots=True)
class DocumentFile:
    """Describes one supported source document file."""

    source_path: Path
    relative_path: Path
    source_system: str
    source_collection: str
    source_path_value: str
    document_id: str


class DocumentFileLoader:
    """Loads supported local files from an export tree."""

    def __init__(self, input_root: Path, transformer: MarkItDownTransformer | None = None):
        self.input_root = input_root.expanduser().resolve()
        self.transformer = transformer or MarkItDownTransformer()

    def load_documents(self) -> Iterable[DocumentFile]:
        """Yield all recursively discovered files supported by the transformer."""
        for path in sorted(self.input_root.rglob("*")):
            if not path.is_file():
                continue
            if not self.transformer.can_handle(path):
                continue

            relative_path = path.relative_to(self.input_root)
            parts = relative_path.parts
            source_system = parts[0] if len(parts) >= 1 else "unknown"
            source_collection = self._derive_source_collection(parts)
            source_path_value = relative_path.as_posix()
            document_id = stable_hash(source_path_value.lower())

            yield DocumentFile(
                source_path=path,
                relative_path=relative_path,
                source_system=source_system,
                source_collection=source_collection,
                source_path_value=source_path_value,
                document_id=document_id,
            )

    @staticmethod
    def _derive_source_collection(parts: tuple[str, ...]) -> str:
        if len(parts) < 2:
            return "default"

        second = parts[1]
        if second.lower() == "raw" and len(parts) >= 3:
            return parts[2]
        return second
