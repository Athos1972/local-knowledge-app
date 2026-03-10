"""Loader für exportierte Confluence-Rohdaten."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from common.logging_setup import AppLogger
from processing.confluence.models import ConfluenceRawPage

logger = AppLogger.get_logger()


class ConfluenceExportLoader:
    """Lädt Confluence-Seiten aus einem Export-Verzeichnisbaum."""

    def __init__(self, input_root: Path):
        self.input_root = input_root.expanduser().resolve()

    def load_pages(self, space_filter: str | None = None) -> Iterable[ConfluenceRawPage]:
        """Iteriert robust über exportierte Seiten-Dateien."""
        if not self.input_root.exists():
            logger.warning("Confluence input root existiert nicht: %s", self.input_root)
            return

        for page_dir, metadata_path in self._iter_page_roots():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                page = self._build_raw_page(payload, metadata_path, page_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Seite konnte nicht geladen werden: %s (%s)", metadata_path, exc)
                continue

            if space_filter and page.space_key.lower() != space_filter.lower():
                continue
            yield page

    def _iter_page_roots(self) -> Iterable[tuple[Path, Path]]:
        """Liefert Seitenverzeichnisse aus der Exportstruktur.

        Erwartete Struktur:
        exports/confluence/<instance>/spaces/<space>/by-id/<pageid>/
          - metadata.json
          - content.storage.xml
        """
        for metadata_path in self.input_root.rglob("metadata.json"):
            page_dir = metadata_path.parent
            if page_dir.name == "by-id":
                continue
            if page_dir.parent.name != "by-id":
                continue
            yield page_dir, metadata_path

    def _build_raw_page(self, payload: dict[str, Any], source_file: Path, page_dir: Path) -> ConfluenceRawPage:
        page_id = str(self._pick(payload, ["page_id", "id", "content_id"], default="")).strip()
        title = str(self._pick(payload, ["title", "page_title", "name"], default="Ohne Titel")).strip()
        space_key = str(self._pick(payload, ["space_key", "space", "spaceKey"], default="unknown")).strip()

        if isinstance(self._pick(payload, ["space"], default=None), dict):
            space_obj = self._pick(payload, ["space"], default={})
            space_key = str(space_obj.get("key", space_key)).strip() or space_key

        body = self._extract_body(payload, page_dir)
        source_url = self._optional_str(self._pick(payload, ["source_url", "url", "_links.webui"]))

        labels = self._normalize_labels(self._pick(payload, ["labels", "metadata.labels"], default=[]))
        ancestors = self._normalize_ancestors(self._pick(payload, ["ancestors"], default=[]))

        parent_title = self._optional_str(self._pick(payload, ["parent_title", "parent.title"]))
        if not parent_title and ancestors:
            parent_title = ancestors[-1]

        attachments = self._normalize_attachments(self._pick(payload, ["attachments"], default=[]))

        return ConfluenceRawPage(
            page_id=page_id or source_file.parent.name,
            space_key=space_key or "unknown",
            title=title or "Ohne Titel",
            body=body,
            source_ref=str(source_file),
            source_url=source_url,
            created_at=self._optional_str(self._pick(payload, ["created_at", "created", "history.createdDate"])),
            updated_at=self._optional_str(self._pick(payload, ["updated_at", "updated", "version.when"])),
            author=self._optional_str(self._pick(payload, ["author", "created_by", "history.createdBy.displayName"])),
            labels=labels,
            parent_title=parent_title,
            ancestors=ancestors,
            page_properties=self._normalize_dict(self._pick(payload, ["page_properties", "properties"], default={})),
            attachments=attachments,
            raw_metadata=payload,
        )

    def _extract_body(self, payload: dict[str, Any], page_dir: Path) -> str:
        xml_path = page_dir / "content.storage.xml"
        if xml_path.exists():
            return xml_path.read_text(encoding="utf-8")

        direct_body = self._pick(payload, ["body_storage", "body", "content", "body.value"], default="")
        if isinstance(direct_body, str) and direct_body.strip():
            return direct_body

        body_obj = payload.get("body")
        if isinstance(body_obj, dict):
            storage = body_obj.get("storage")
            if isinstance(storage, dict):
                return str(storage.get("value", ""))
        return ""

    def _pick(self, payload: dict[str, Any], paths: list[str], default: Any = None) -> Any:
        for path in paths:
            current: Any = payload
            success = True
            for part in path.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    success = False
                    break
            if success:
                return current
        return default

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _normalize_labels(value: Any) -> list[str]:
        if isinstance(value, list):
            labels: list[str] = []
            for item in value:
                if isinstance(item, str):
                    labels.append(item.strip())
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("label")
                    if isinstance(name, str) and name.strip():
                        labels.append(name.strip())
            return [label for label in labels if label]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    @staticmethod
    def _normalize_ancestors(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif isinstance(item, dict):
                title = item.get("title")
                if isinstance(title, str) and title.strip():
                    result.append(title.strip())
        return result

    @staticmethod
    def _normalize_attachments(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"name": item})
        return normalized

    @staticmethod
    def _normalize_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}
