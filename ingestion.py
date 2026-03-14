from __future__ import annotations

"""Document ingestion from markdown with frontmatter metadata mapping."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import frontmatter
from llama_index.core import Document


@dataclass(frozen=True)
class IngestionStats:
    """Basic ingestion statistics for observability/logging."""

    files_scanned: int
    documents_loaded: int


class MarkdownIngestor:
    """Load markdown files and map frontmatter fields into LlamaIndex metadata."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def load_documents(self) -> tuple[list[Document], IngestionStats]:
        """Read all markdown files recursively and convert to LlamaIndex documents."""
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory does not exist: {self.data_dir}")

        files = sorted(self.data_dir.rglob("*.md"))
        documents: list[Document] = []

        for file_path in files:
            post = frontmatter.load(file_path)
            metadata = self._build_metadata(file_path=file_path, fm=post.metadata)
            text = post.content.strip()
            if not text:
                continue
            documents.append(Document(text=text, metadata=metadata))

        stats = IngestionStats(files_scanned=len(files), documents_loaded=len(documents))
        return documents, stats

    @staticmethod
    def _build_metadata(file_path: Path, fm: dict[str, Any]) -> dict[str, Any]:
        """Normalize canonical metadata and preserve all raw frontmatter fields."""
        source = str(fm.get("source") or fm.get("system") or "unknown").lower()
        source = MarkdownIngestor._normalize_source(source)

        metadata: dict[str, Any] = {
            "source": source,
            "jira_status": fm.get("jira_status") or fm.get("status"),
            "date": fm.get("date") or fm.get("updated") or fm.get("created"),
            "source_link": fm.get("source_link") or fm.get("url") or fm.get("link"),
            "title": fm.get("title") or file_path.stem,
            "path": str(file_path),
        }

        for key, value in fm.items():
            metadata.setdefault(str(key), value)

        return metadata

    @staticmethod
    def _normalize_source(source: str) -> str:
        if "jira" in source:
            return "jira"
        if "confluence" in source:
            return "confluence"
        if "web" in source:
            return "web"
        return "other"


def iter_markdown_paths(data_dir: str | Path) -> Iterable[Path]:
    """Iterate markdown paths for auxiliary tooling and diagnostics."""

    return sorted(Path(data_dir).rglob("*.md"))
