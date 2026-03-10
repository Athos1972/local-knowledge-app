"""Persistenter Zustand für inkrementelle Confluence-Transformation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TransformStateRecord:
    """Letzter Stand einer transformierten Seite."""

    source_checksum: str
    output_checksum: str
    output_file: str
    updated_at: str


@dataclass(slots=True)
class TransformState:
    """Inkrementeller Zustand über alle Seiten."""

    pages: dict[str, TransformStateRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> TransformState:
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_pages: dict[str, Any] = payload.get("pages", {})
        pages: dict[str, TransformStateRecord] = {}
        for page_id, record in raw_pages.items():
            pages[page_id] = TransformStateRecord(
                source_checksum=str(record.get("source_checksum", "")),
                output_checksum=str(record.get("output_checksum", "")),
                output_file=str(record.get("output_file", "")),
                updated_at=str(record.get("updated_at", "")),
            )
        return cls(pages=pages)

    def save(self, path: Path) -> None:
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {"pages": {page_id: asdict(record) for page_id, record in self.pages.items()}}
