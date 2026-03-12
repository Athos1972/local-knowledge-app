from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import mimetypes

from .models import TransformResult

_SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".epub",
}


@dataclass(slots=True)
class MarkItDownTransformer:
    """Adapter around MarkItDown to keep conversion dependency replaceable."""

    name: str = "markitdown"

    @property
    def version(self) -> str | None:
        try:
            from importlib.metadata import version

            return version("markitdown")
        except Exception:
            return None

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in _SUPPORTED_EXTENSIONS

    def transform(self, path: Path) -> TransformResult:
        if not self.can_handle(path):
            return TransformResult(
                source_path=path,
                markdown="",
                success=False,
                warnings=[f"Unsupported extension: {path.suffix.lower()}"]
            )

        if not path.exists():
            return TransformResult(
                source_path=path,
                markdown="",
                success=False,
                error="Source file does not exist",
            )

        try:
            from markitdown import MarkItDown
        except Exception as exc:
            return TransformResult(
                source_path=path,
                markdown="",
                success=False,
                error="markitdown dependency is not installed",
                warnings=[str(exc)],
            )

        warnings: list[str] = []
        try:
            converter = MarkItDown()
            converted = converter.convert(str(path))
            markdown = _extract_markdown(converted)
            if not markdown.strip():
                warnings.append("Transformer returned empty markdown")

            metadata = _build_technical_metadata(path)
            return TransformResult(
                source_path=path,
                markdown=markdown,
                metadata=metadata,
                warnings=warnings,
                success=True,
            )
        except Exception as exc:
            return TransformResult(
                source_path=path,
                markdown="",
                metadata=_build_technical_metadata(path),
                warnings=warnings,
                success=False,
                error=f"markitdown conversion failed: {exc}",
            )


def _extract_markdown(converted: Any) -> str:
    if isinstance(converted, str):
        return converted

    for candidate_attr in ("text_content", "markdown", "content", "text"):
        value = getattr(converted, candidate_attr, None)
        if isinstance(value, str):
            return value

    return str(converted)


def _build_technical_metadata(path: Path) -> dict[str, Any]:
    mime_type, _ = mimetypes.guess_type(str(path))
    stat = path.stat()
    return {
        "file_name": path.name,
        "extension": path.suffix.lower(),
        "mime_type": mime_type or "application/octet-stream",
        "source_size_bytes": stat.st_size,
        "source_modified_at": stat.st_mtime,
    }
