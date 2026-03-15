from __future__ import annotations

import csv
from pathlib import Path

from common.config import AppConfig
from processing.terminology.candidates import TerminologyCandidateReviewService
from processing.terminology.excel import TerminologyExcelService
from processing.terminology.loader import TerminologyLoader, TerminologySettings
from processing.terminology.validator import TerminologyValidator


def _write_config(root: Path, with_duplicate_alias: bool = False, with_invalid_relation: bool = False) -> None:
    cfg = root / "config" / "terminology"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.yml").write_text(
        """
settings:
  enabled: true
  case_insensitive_default: true
  normalize_hyphen_whitespace: true
  block_min_terms: 2
  show_aliases_in_block: false
  candidate_detection_enabled: true
  candidate_patterns:
    - '\\b[A-Z][A-Z0-9\\-]{2,}\\b'
""",
        encoding="utf-8",
    )
    (cfg / "sources.yml").write_text(
        """
sources:
  confluence:
    mode: annotate_and_block
    candidates_enabled: true
  jira:
    mode: annotate_and_block
    candidates_enabled: true
""",
        encoding="utf-8",
    )

    duplicate_alias_entry = """
  - id: p2
    canonical: Project Two
    label: Project Two
    description: Desc
    term_class: business
    aliases: [PM]
    relations: []
    applies_to: [confluence]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 20
""" if with_duplicate_alias else ""

    invalid_relation = "unknown" if with_invalid_relation else "p1"
    (cfg / "terms.yml").write_text(
        f"""
terms:
  - id: p1
    canonical: Project One
    label: Project One
    description: Desc
    term_class: business
    aliases: [PM]
    relations:
      - type: related_to
        target_term_id: {invalid_relation}
    applies_to: [confluence, jira]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 10
{duplicate_alias_entry}
""",
        encoding="utf-8",
    )


def test_loader_loads_existing_config(tmp_path: Path) -> None:
    _write_config(tmp_path)
    config = TerminologyLoader(tmp_path / "config" / "terminology").load()
    assert "p1" in config.terms_by_id
    assert config.source_modes["confluence"].mode == "annotate_and_block"


def test_validator_happy_path(tmp_path: Path) -> None:
    _write_config(tmp_path)
    result = TerminologyValidator(tmp_path / "config" / "terminology").validate()
    assert result.errors == []


def test_validator_duplicate_alias_error(tmp_path: Path) -> None:
    _write_config(tmp_path, with_duplicate_alias=True)
    result = TerminologyValidator(tmp_path / "config" / "terminology").validate()
    assert any(issue.code == "duplicate_alias" for issue in result.errors)


def test_validator_invalid_relation_error(tmp_path: Path) -> None:
    _write_config(tmp_path, with_invalid_relation=True)
    result = TerminologyValidator(tmp_path / "config" / "terminology").validate()
    assert any(issue.code == "invalid_relation_target" for issue in result.errors)


def test_xlsx_export_and_import_roundtrip(tmp_path: Path) -> None:
    _write_config(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    service = TerminologyExcelService(tmp_path / "config" / "terminology", reports)

    output = reports / "terminology.xlsx"
    service.export_xlsx(output)
    assert output.exists()

    result = service.import_xlsx(output, dry_run=True)
    assert result.terms == 1
    assert result.aliases == 1


def test_candidates_review_basics(tmp_path: Path) -> None:
    _write_config(tmp_path)
    candidates_path = tmp_path / "reports" / "terminology_candidates.csv"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)

    with candidates_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_type", "term", "count", "first_seen_file", "example_context", "already_known"])
        writer.writerow(["confluence", "PM", "2", "file.md", "ctx", "false"])
        writer.writerow(["jira", "NEU", "4", "issue.md", "ctx", "false"])

    rows = TerminologyCandidateReviewService(tmp_path / "config" / "terminology", candidates_path).enrich()

    assert len(rows) == 2
    known_row = [row for row in rows if row.term == "PM"][0]
    assert known_row.already_known == "true"
    assert known_row.suggested_action == "add_alias"
    new_row = [row for row in rows if row.term == "NEU"][0]
    assert new_row.suggested_action == "new_term"


def test_loader_reads_file_names_from_app_toml(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "config" / "terminology"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "custom_settings.yml").write_text(
        """
settings:
  enabled: true
""",
        encoding="utf-8",
    )
    (cfg / "custom_sources.yml").write_text(
        """
sources:
  confluence:
    mode: annotate_and_block
    candidates_enabled: true
""",
        encoding="utf-8",
    )
    (cfg / "custom_terms.yml").write_text(
        """
terms:
  - id: x
    canonical: X
    label: X
    description: Desc
    term_class: business
    aliases: []
    relations: []
    applies_to: [confluence]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 10
""",
        encoding="utf-8",
    )

    app_toml = tmp_path / "app.toml"
    app_toml.write_text(
        """
[terminology]
settings_file = "custom_settings.yml"
sources_file = "custom_sources.yml"
terms_file = "custom_terms.yml"
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_CONFIG_FILE", str(app_toml))
    AppConfig._config = None
    AppConfig._env_loaded = True

    config = TerminologyLoader(cfg).load()
    assert "x" in config.terms_by_id


def test_validator_uses_app_toml_file_names(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "config" / "terminology"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "s.yml").write_text(
        """
settings:
  enabled: true
""",
        encoding="utf-8",
    )
    (cfg / "o.yml").write_text(
        """
sources:
  jira:
    mode: off
    candidates_enabled: false
""",
        encoding="utf-8",
    )
    (cfg / "t.yml").write_text(
        """
terms:
  - id: z
    canonical: Z
    label: Z
    description: Desc
    term_class: business
    aliases: []
    relations: []
    applies_to: [jira]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 1
""",
        encoding="utf-8",
    )

    app_toml = tmp_path / "app2.toml"
    app_toml.write_text(
        """
[terminology.files]
settings = "s.yml"
sources = "o.yml"
terms = "t.yml"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(app_toml))
    AppConfig._config = None
    AppConfig._env_loaded = True

    result = TerminologyValidator(cfg).validate()
    assert result.errors == []


def test_loader_default_candidate_pattern_is_a_working_regex() -> None:
    settings = TerminologySettings()
    assert settings.candidate_patterns == [r"\b[A-ZÄÖÜ][A-ZÄÖÜ0-9]{1,}(?:-[A-Za-zÄÖÜäöü0-9]+)*\b"]


def test_loader_parses_yaml_boolean_off_as_off_mode() -> None:
    parsed = TerminologyLoader.parse_sources(
        {
            "sources": {
                "scrape": {
                    "mode": False,
                }
            }
        }
    )

    assert parsed["scrape"].mode == "off"
    assert parsed["scrape"].candidates_enabled is False
