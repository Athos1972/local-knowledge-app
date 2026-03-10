"""Persistenter Zustand für inkrementelle Publish-Läufe."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PublishStateRecord:
    """Aktueller Publish-Stand einer Input-Datei."""

    source_checksum: str
    output_checksum: str
    output_file: str
    updated_at: str


@dataclass(slots=True)
class PublishState:
    """Inkrementeller Zustand für Staging-Dateien."""

    files: dict[str, PublishStateRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PublishState:
        """Lädt Publish-State aus JSON, falls vorhanden."""
        target = path.expanduser().resolve()
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_files: dict[str, Any] = payload.get("files", {})
        files: dict[str, PublishStateRecord] = {}
        for key, value in raw_files.items():
            files[str(key)] = PublishStateRecord(
                source_checksum=str(value.get("source_checksum", "")),
                output_checksum=str(value.get("output_checksum", "")),
                output_file=str(value.get("output_file", "")),
                updated_at=str(value.get("updated_at", "")),
            )
        return cls(files=files)

    def save(self, path: Path) -> None:
        """Persistiert den State als JSON-Datei."""
        target = path.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Zustand in ein Dictionary."""
        return {"files": {key: asdict(value) for key, value in self.files.items()}}
