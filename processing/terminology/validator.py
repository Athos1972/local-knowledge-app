from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from pathlib import Path
from typing import Any

import yaml

from processing.terminology.loader import DEFAULT_SOURCE_TYPES, TerminologyLoader


logger = logging.getLogger(__name__)

ALLOWED_TERM_CLASSES = {"business", "system", "organisation", "process", "technology", "person"}
ALLOWED_ANNOTATE_POLICIES = {"first_occurrence", "never"}
ALLOWED_BLOCK_POLICIES = {"include", "exclude"}
AMBIGUOUS_SHORTFORMS = {"PM", "CI", "PO"}


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str


@dataclass(slots=True)
class ValidationStats:
    terms: int = 0
    aliases: int = 0
    relations: int = 0
    sources: int = 0


@dataclass(slots=True)
class ValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    stats: ValidationStats = field(default_factory=ValidationStats)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "info": self.info,
            "stats": asdict(self.stats),
            "is_valid": self.is_valid,
        }


class TerminologyValidator:
    def __init__(self, config_root: Path) -> None:
        self._config_root = config_root

    def validate(self) -> ValidationResult:
        result = ValidationResult()
        loader = TerminologyLoader(self._config_root)
        self._validate_yaml_readable(result)

        if result.errors:
            return result

        try:
            config = loader.load()
        except Exception as exc:
            result.errors.append(ValidationIssue(code="load_failed", message=str(exc), path=str(self._config_root)))
            return result

        terms = config.terms_by_id
        raw_terms = (loader._load_yaml('terms.yml').get('terms', []) if hasattr(loader, '_load_yaml') else [])
        result.stats.terms = len(terms)
        result.stats.sources = len(config.source_modes)
        result.stats.aliases = sum(len(term.aliases) for term in terms.values())
        result.stats.relations = sum(len(term.relations) for term in terms.values())

        canonical_to_term: dict[str, str] = {}
        alias_to_term: dict[str, str] = {}

        for term_id, term in terms.items():
            base_path = f"terms[{term_id}]"
            for field_name in ["term_id", "canonical", "label", "description", "term_class"]:
                if not getattr(term, "term_id" if field_name == "term_id" else field_name):
                    result.errors.append(ValidationIssue("required_field", f"Missing field '{field_name}'", f"{base_path}.{field_name}"))

            canonical_key = term.canonical.lower()
            if canonical_key in canonical_to_term and canonical_to_term[canonical_key] != term_id:
                result.errors.append(
                    ValidationIssue("duplicate_canonical", f"Canonical '{term.canonical}' already used by '{canonical_to_term[canonical_key]}'", f"{base_path}.canonical")
                )
            canonical_to_term[canonical_key] = term_id

            if term.term_class not in ALLOWED_TERM_CLASSES:
                result.errors.append(ValidationIssue("invalid_term_class", f"Unknown term_class '{term.term_class}'", f"{base_path}.term_class"))

            if term.annotate_policy not in ALLOWED_ANNOTATE_POLICIES:
                result.errors.append(ValidationIssue("invalid_annotate_policy", f"Unknown annotate_policy '{term.annotate_policy}'", f"{base_path}.annotate_policy"))

            if term.block_policy not in ALLOWED_BLOCK_POLICIES:
                result.errors.append(ValidationIssue("invalid_block_policy", f"Unknown block_policy '{term.block_policy}'", f"{base_path}.block_policy"))

            for source_type in term.applies_to:
                if source_type not in DEFAULT_SOURCE_TYPES:
                    result.errors.append(
                        ValidationIssue("unknown_source_type", f"Unknown source_type '{source_type}'", f"{base_path}.applies_to")
                    )

            if term.term_class == "person" and term.annotate_policy != "never":
                result.warnings.append(
                    ValidationIssue("person_annotation", "person terms should use annotate_policy='never' in V1", f"{base_path}.annotate_policy")
                )

            if term.canonical.upper() in AMBIGUOUS_SHORTFORMS:
                result.warnings.append(
                    ValidationIssue("ambiguous_shortform", f"Canonical shortform '{term.canonical}' may be ambiguous", f"{base_path}.canonical")
                )

            for alias in term.aliases:
                alias_key = alias.lower()
                if alias_key in alias_to_term and alias_to_term[alias_key] != term_id:
                    result.errors.append(
                        ValidationIssue(
                            "duplicate_alias",
                            f"Alias '{alias}' already assigned to '{alias_to_term[alias_key]}'",
                            f"{base_path}.aliases",
                        )
                    )
                alias_to_term[alias_key] = term_id
                if alias.upper() in AMBIGUOUS_SHORTFORMS:
                    result.warnings.append(
                        ValidationIssue("ambiguous_shortform", f"Alias shortform '{alias}' may be ambiguous", f"{base_path}.aliases")
                    )

            for relation in term.relations:
                if relation.target_id not in terms:
                    result.errors.append(
                        ValidationIssue(
                            "invalid_relation_target",
                            f"Relation target '{relation.target_id}' does not exist",
                            f"{base_path}.relations",
                        )
                    )

        seen_ids: set[str] = set()
        for index, entry in enumerate(raw_terms if isinstance(raw_terms, list) else []):
            if not isinstance(entry, dict):
                continue
            term_id = str(entry.get('id', '')).strip()
            if term_id in seen_ids:
                result.errors.append(ValidationIssue('duplicate_id', f"Duplicate id '{term_id}'", f"terms[{index}].id"))
            if term_id:
                seen_ids.add(term_id)

        result.info.append(f"Loaded {result.stats.terms} terms from {self._config_root}")
        logger.info(
            "Terminology validation complete: errors=%s warnings=%s terms=%s",
            len(result.errors),
            len(result.warnings),
            result.stats.terms,
        )
        return result

    def _validate_yaml_readable(self, result: ValidationResult) -> None:
        for filename in ["settings.yml", "sources.yml", "terms.yml"]:
            path = self._config_root / filename
            if not path.exists():
                result.errors.append(ValidationIssue("missing_file", f"Missing file '{filename}'", str(path)))
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    yaml.safe_load(handle)
            except Exception as exc:
                result.errors.append(ValidationIssue("invalid_yaml", str(exc), str(path)))
