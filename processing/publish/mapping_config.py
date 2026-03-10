"""Konfigurationsmodelle für den Confluence-Publish."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.config import AppConfig

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(slots=True)
class ConfluencePublishConfig:
    """Typisierte Konfiguration für den Publish-Schritt."""

    input_root: Path
    output_root: Path
    manifests_dir: Path
    mode: str = "copy"
    space_map: dict[str, str] = field(default_factory=dict)
    fallback_path: str = "_unmapped/confluence"
    publish_unmapped: bool = True

    @classmethod
    def from_sources(
        cls,
        input_root_override: str | None = None,
        output_root_override: str | None = None,
        mapping_config_path: str | None = None,
    ) -> ConfluencePublishConfig:
        """Lädt Konfiguration aus APP-Config oder optionaler TOML-Datei."""
        data_root = Path.home() / "local-knowledge-data"

        config_payload: dict[str, Any]
        if mapping_config_path:
            path = Path(mapping_config_path).expanduser().resolve()
            with path.open("rb") as handle:
                config_payload = tomllib.load(handle)
        else:
            default_mapping_config = Path("config/publish_confluence.toml").resolve()
            if default_mapping_config.exists():
                with default_mapping_config.open("rb") as handle:
                    config_payload = tomllib.load(handle)
            else:
                config_payload = AppConfig.load()

        section = cls._read_confluence_section(config_payload)
        defaults = section.get("defaults", {}) if isinstance(section.get("defaults"), dict) else {}

        input_root_value = input_root_override or section.get("input_root") or str(data_root / "staging" / "confluence")
        output_root_value = output_root_override or section.get("output_root") or str(data_root / "domains")
        manifests_dir_value = section.get("manifests_dir") or str(data_root / "system" / "confluence_publish")

        return cls(
            input_root=Path(input_root_value).expanduser().resolve(),
            output_root=Path(output_root_value).expanduser().resolve(),
            manifests_dir=Path(manifests_dir_value).expanduser().resolve(),
            mode=str(section.get("mode", "copy")),
            space_map={str(k): str(v) for k, v in (section.get("space_map") or {}).items()},
            fallback_path=str(defaults.get("fallback_path", "_unmapped/confluence")),
            publish_unmapped=bool(defaults.get("publish_unmapped", True)),
        )

    @staticmethod
    def _read_confluence_section(config_payload: dict[str, Any]) -> dict[str, Any]:
        publish = config_payload.get("publish", {})
        if isinstance(publish, dict) and isinstance(publish.get("confluence"), dict):
            return publish["confluence"]

        confluence = config_payload.get("confluence_publish", {})
        if isinstance(confluence, dict):
            return confluence

        return {}
