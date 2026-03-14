from __future__ import annotations

from pathlib import Path

from processing.terminology.service import TerminologyService


def _write_configs(root: Path) -> None:
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
  scrape:
    mode: off
    candidates_enabled: false
""",
        encoding="utf-8",
    )
    (cfg / "terms.yml").write_text(
        """
terms:
  - id: isu
    canonical: ISU
    label: SAP Industry Solution Utilities
    description: Utilities-Lösung
    term_class: system
    aliases: [IS-U]
    relations: []
    applies_to: [confluence, jira]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 10

  - id: eda
    canonical: EDA
    label: Energy Data Exchange Austria
    description: Datenaustausch
    term_class: organisation
    aliases: []
    relations:
      - type: related_to
        target: ponton
    applies_to: [confluence, jira]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 20

  - id: ponton
    canonical: PONTON
    label: PONTON GmbH
    description: Anbieter
    term_class: organisation
    aliases: []
    relations:
      - type: related_to
        target: eda
    applies_to: [confluence, jira]
    annotate_policy: first_occurrence
    block_policy: include
    case_sensitive: false
    priority: 21
""",
        encoding="utf-8",
    )


def test_yaml_loading_and_scope_filtering(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=tmp_path / "reports")

    result = service.apply_to_text("IS-U im Confluence-Text", "confluence", source_ref="file.md")

    assert "IS-U (SAP Industry Solution Utilities)" in result.text
    assert "## Terminologie" not in result.text  # block_min_terms=2


def test_alias_vs_related_to_behavior(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=tmp_path / "reports")

    text = "IS-U spricht mit EDA. PONTON ist ebenfalls beteiligt."
    result = service.apply_to_text(text, "jira", source_ref="issue.md")

    assert "IS-U (SAP Industry Solution Utilities)" in result.text
    assert "EDA (Energy Data Exchange Austria)" in result.text
    assert "- EDA: Energy Data Exchange Austria" in result.text
    assert "Verwandte Begriffe: PONTON" in result.text


def test_only_first_occurrence_is_annotated(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=tmp_path / "reports")

    result = service.apply_to_text("ISU ist wichtig. ISU bleibt wichtig.", "confluence", source_ref="page.md")

    assert result.text.count("ISU (SAP Industry Solution Utilities)") == 1
    assert result.text.count("ISU") >= 2


def test_terminology_block_generation(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=tmp_path / "reports")

    result = service.apply_to_text("EDA und PONTON werden erwähnt.", "confluence", source_ref="page.md")

    assert result.block_added is True
    assert "## Terminologie" in result.text
    assert "- EDA: Energy Data Exchange Austria" in result.text


def test_scrape_is_off(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=tmp_path / "reports")

    original = "ISU und EDA"
    result = service.apply_to_text(original, "scrape", source_ref="scrape.md")

    assert result.text == original
    assert result.annotations_applied == 0
    assert result.block_added is False
