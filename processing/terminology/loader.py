from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

import yaml

from common.config import AppConfig
from processing.terminology.models import SourceMode, TerminologyRelation, TerminologyTerm


logger = logging.getLogger(__name__)

DEFAULT_SOURCE_TYPES = {"confluence", "jira", "mail", "teams", "scrape"}
ALLOWED_SOURCE_MODES = {"off", "annotate_and_block", "block_only"}

DEFAULT_SETTINGS_FILE = "settings.yml"
DEFAULT_SOURCES_FILE = "sources.yml"
DEFAULT_TERMS_FILE = "terms.yml"
DEFAULT_CANDIDATE_EXCLUDE_FILE = "candidate_exclude.yml"


@dataclass(frozen=True, slots=True)
class TerminologyFileNames:
    """Terminology file names resolved from app config with safe defaults."""

    settings: str = DEFAULT_SETTINGS_FILE
    sources: str = DEFAULT_SOURCES_FILE
    terms: str = DEFAULT_TERMS_FILE
    candidate_exclude: str = DEFAULT_CANDIDATE_EXCLUDE_FILE


def resolve_terminology_file_names() -> TerminologyFileNames:
    """Resolve terminology file names from `config/app.toml` with defaults.

    Supported keys:
    - `[terminology] settings_file/sources_file/terms_file/candidate_exclude_file`
    - `[terminology.files] settings/sources/terms/candidate_exclude`

    The app config cache is refreshed to avoid stale file-name overrides when
    tests or scripts switch `APP_CONFIG_FILE` between calls.
    """
    AppConfig._config = None

    def _resolve(*keys: str, default: str) -> str:
        value = AppConfig.get(*keys, default=None)
        if value is None:
            return default
        rendered = str(value).strip()
        return rendered or default

    return TerminologyFileNames(
        settings=_resolve("terminology", "files", "settings", default=_resolve("terminology", "settings_file", default=DEFAULT_SETTINGS_FILE)),
        sources=_resolve("terminology", "files", "sources", default=_resolve("terminology", "sources_file", default=DEFAULT_SOURCES_FILE)),
        terms=_resolve("terminology", "files", "terms", default=_resolve("terminology", "terms_file", default=DEFAULT_TERMS_FILE)),
        candidate_exclude=_resolve(
            "terminology",
            "files",
            "candidate_exclude",
            default=_resolve("terminology", "candidate_exclude_file", default=DEFAULT_CANDIDATE_EXCLUDE_FILE),
        ),
    )


@dataclass(slots=True)
class TerminologySettings:
    enabled: bool = True
    case_insensitive_default: bool = True
    normalize_hyphen_whitespace: bool = True
    block_min_terms: int = 2
    show_aliases_in_block: bool = False
    candidate_detection_enabled: bool = True
    candidate_patterns: list[str] = field(default_factory=lambda: [r"\\b[A-ZÄÖÜ][A-ZÄÖÜ0-9\\-]{2,}\\b"])


@dataclass(slots=True)
class TerminologyConfig:
    settings: TerminologySettings
    source_modes: dict[str, SourceMode]
    terms_by_id: dict[str, TerminologyTerm]


class TerminologyLoader:
    def __init__(self, config_root: Path) -> None:
        self._config_root = config_root
        self.file_names = resolve_terminology_file_names()

    def load(self) -> TerminologyConfig:
        settings_data = self._load_yaml(self.file_names.settings)
        sources_data = self._load_yaml(self.file_names.sources)
        terms_data = self._load_yaml(self.file_names.terms)

        settings = self.parse_settings(settings_data)
        source_modes = self.parse_sources(sources_data)
        terms = self.parse_terms(terms_data)
        logger.info("Terminology config loaded: terms=%s sources=%s", len(terms), len(source_modes))
        return TerminologyConfig(settings=settings, source_modes=source_modes, terms_by_id=terms)

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        path = self._config_root / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing terminology config file: {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Invalid YAML root in {path}")
        return data

    @staticmethod
    def parse_settings(data: dict[str, Any]) -> TerminologySettings:
        raw = data.get("settings", data)
        return TerminologySettings(
            enabled=bool(raw.get("enabled", True)),
            case_insensitive_default=bool(raw.get("case_insensitive_default", True)),
            normalize_hyphen_whitespace=bool(raw.get("normalize_hyphen_whitespace", True)),
            block_min_terms=int(raw.get("block_min_terms", 2)),
            show_aliases_in_block=bool(raw.get("show_aliases_in_block", False)),
            candidate_detection_enabled=bool(raw.get("candidate_detection_enabled", True)),
            candidate_patterns=list(raw.get("candidate_patterns", [r"\\b[A-ZÄÖÜ][A-ZÄÖÜ0-9\\-]{2,}\\b"])),
        )

    @staticmethod
    def parse_sources(data: dict[str, Any]) -> dict[str, SourceMode]:
        source_entries = data.get("sources", {})
        if not isinstance(source_entries, dict):
            raise ValueError("'sources' must be a mapping")

        parsed: dict[str, SourceMode] = {}
        for source_name, source_data in source_entries.items():
            if not isinstance(source_data, dict):
                continue
            mode = str(source_data.get("mode", "off")).strip()
            parsed[source_name] = SourceMode(
                mode=mode,
                candidates_enabled=bool(source_data.get("candidates_enabled", False)),
                enabled=source_data.get("enabled"),
            )
        return parsed

    @staticmethod
    def parse_terms(data: dict[str, Any]) -> dict[str, TerminologyTerm]:
        raw_terms = data.get("terms", [])
        if not isinstance(raw_terms, list):
            raise ValueError("'terms' must be a list")

        terms: dict[str, TerminologyTerm] = {}
        for entry in raw_terms:
            if not isinstance(entry, dict):
                continue
            term_id = str(entry.get("id", "")).strip()
            if not term_id:
                continue
            relations = []
            for rel in entry.get("relations", []) or []:
                if not isinstance(rel, dict):
                    continue
                rel_type = str(rel.get("type", "")).strip()
                target_id = str(
                    rel.get("target_term_id")
                    or rel.get("target_id")
                    or rel.get("target")
                    or ""
                ).strip()
                target_label = str(rel.get("target_label", "")).strip() or None
                note = str(rel.get("note", "")).strip() or None
                if rel_type and target_id:
                    relations.append(
                        TerminologyRelation(
                            relation_type=rel_type,
                            target_id=target_id,
                            target_label=target_label,
                            note=note,
                        )
                    )

            terms[term_id] = TerminologyTerm(
                term_id=term_id,
                canonical=str(entry.get("canonical", term_id)).strip(),
                label=str(entry.get("label", entry.get("canonical", term_id))).strip(),
                description=str(entry.get("description", "")).strip(),
                term_class=str(entry.get("term_class", "business")).strip(),
                aliases=[str(v).strip() for v in (entry.get("aliases", []) or []) if str(v).strip()],
                relations=relations,
                applies_to=[str(v).strip() for v in (entry.get("applies_to", []) or []) if str(v).strip()],
                annotate_policy=str(entry.get("annotate_policy", "first_occurrence")).strip(),
                block_policy=str(entry.get("block_policy", "include")).strip(),
                case_sensitive=bool(entry.get("case_sensitive", False)),
                priority=int(entry.get("priority", 100)),
            )

        return terms


def write_yaml_files(
    config_root: Path,
    settings: TerminologySettings,
    sources: dict[str, SourceMode],
    terms: list[TerminologyTerm],
    *,
    file_names: TerminologyFileNames | None = None,
) -> None:
    config_root.mkdir(parents=True, exist_ok=True)
    names = file_names or resolve_terminology_file_names()

    settings_payload = {
        "settings": {
            "enabled": settings.enabled,
            "case_insensitive_default": settings.case_insensitive_default,
            "normalize_hyphen_whitespace": settings.normalize_hyphen_whitespace,
            "block_min_terms": settings.block_min_terms,
            "show_aliases_in_block": settings.show_aliases_in_block,
            "candidate_detection_enabled": settings.candidate_detection_enabled,
            "candidate_patterns": settings.candidate_patterns,
        }
    }

    sources_payload = {
        "sources": {
            source_name: {
                "mode": source_mode.mode,
                "candidates_enabled": source_mode.candidates_enabled,
            }
            for source_name, source_mode in sorted(sources.items())
        }
    }

    terms_payload = {
        "terms": [
            {
                "id": term.term_id,
                "canonical": term.canonical,
                "label": term.label,
                "description": term.description,
                "term_class": term.term_class,
                "aliases": term.aliases,
                "relations": [
                    {
                        "type": relation.relation_type,
                        "target_term_id": relation.target_id,
                        **({"target_label": relation.target_label} if relation.target_label else {}),
                        **({"note": relation.note} if relation.note else {}),
                    }
                    for relation in term.relations
                ],
                "applies_to": term.applies_to,
                "annotate_policy": term.annotate_policy,
                "block_policy": term.block_policy,
                "case_sensitive": term.case_sensitive,
                "priority": term.priority,
            }
            for term in sorted(terms, key=lambda item: (item.priority, item.term_id))
        ]
    }

    (config_root / names.settings).write_text(yaml.safe_dump(settings_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (config_root / names.sources).write_text(yaml.safe_dump(sources_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (config_root / names.terms).write_text(yaml.safe_dump(terms_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
