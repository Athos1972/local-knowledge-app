"""Pfadauflösung für Confluence-Publish in Domain-Strukturen."""

from __future__ import annotations

from pathlib import Path

from processing.publish.mapping_config import ConfluencePublishConfig
from processing.publish.models import ResolvedPublishTarget, StagingDocument


class PublishPathResolver:
    """Bestimmt den Zielpfad basierend auf Space-Mapping."""

    def __init__(self, config: ConfluencePublishConfig):
        self._config = config

    def resolve(self, document: StagingDocument) -> ResolvedPublishTarget:
        """Löst den finalen Zielpfad für ein Staging-Dokument auf."""
        space_key = document.space_key
        file_name = document.input_file.name

        mapped_domain = self._config.space_map.get(space_key)
        if mapped_domain:
            output_file = self._config.output_root / mapped_domain / file_name
            return ResolvedPublishTarget(
                output_file=output_file,
                domain_path=mapped_domain,
                mapping_status="mapped",
            )

        fallback_root = self._config.fallback_path.strip("/")
        domain_path = f"{fallback_root}/{space_key or '_missing_space'}"
        output_file = self._config.output_root / domain_path / file_name
        return ResolvedPublishTarget(
            output_file=output_file,
            domain_path=domain_path,
            mapping_status="unmapped",
        )
