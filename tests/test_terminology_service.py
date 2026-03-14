from __future__ import annotations

import csv
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
    (cfg / "candidate_exclude.yml").write_text(
        """
candidate_exclude:
  - INFO
  - API
  - URL
  - BSBX*
""",
        encoding="utf-8",
    )


def _read_candidates(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def test_candidates_are_aggregated_and_counted(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    reports_root = tmp_path / "reports"
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=reports_root)

    service.apply_to_text("INFO BSBX123 ALPHA ALPHA", "confluence", source_ref="doc-1.md")
    service.apply_to_text("ALPHA ALPHA", "confluence", source_ref="doc-2.md")

    rows = _read_candidates(reports_root / "terminology_candidates.csv")
    assert len(rows) == 1
    assert rows[0]["source_type"] == "confluence"
    assert rows[0]["term"] == "ALPHA"
    assert rows[0]["count"] == "4"
    assert rows[0]["first_seen_file"] == "doc-1.md"
    assert rows[0]["last_seen_file"] == "doc-2.md"


def test_candidates_are_aggregated_per_source(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    reports_root = tmp_path / "reports"
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=reports_root)

    service.apply_to_text("DELTA", "confluence", source_ref="page-1.md")
    service.apply_to_text("DELTA", "jira", source_ref="issue-1.md")

    rows = _read_candidates(reports_root / "terminology_candidates.csv")
    assert len(rows) == 2
    assert {row["source_type"] for row in rows} == {"confluence", "jira"}


def test_existing_review_fields_are_preserved(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    reports_root = tmp_path / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    csv_path = reports_root / "terminology_candidates.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "source_type",
            "term",
            "count",
            "first_seen_file",
            "example_context",
            "already_known",
            "suggested_action",
            "selected_term_id",
            "reviewer_status",
            "reviewer_note",
        ])
        writer.writerow(["confluence", "GAMMA", "2", "old.md", "ctx", "true", "add_alias", "t-1", "done", "keep me"])

    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=reports_root)
    service.apply_to_text("GAMMA", "confluence", source_ref="new.md")

    rows = _read_candidates(csv_path)
    assert len(rows) == 1
    assert rows[0]["count"] == "3"
    assert rows[0]["already_known"] == "true"
    assert rows[0]["suggested_action"] == "add_alias"
    assert rows[0]["selected_term_id"] == "t-1"
    assert rows[0]["reviewer_status"] == "done"
    assert rows[0]["reviewer_note"] == "keep me"


def test_excludes_are_case_insensitive_and_support_wildcards(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    reports_root = tmp_path / "reports"
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=reports_root)

    service.apply_to_text("info API Url BSBX123 BSBX-TEST KEEP", "confluence", source_ref="d.md")

    rows = _read_candidates(reports_root / "terminology_candidates.csv")
    assert len(rows) == 1
    assert rows[0]["term"] == "KEEP"


def test_candidate_noop_is_stable(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    reports_root = tmp_path / "reports"
    service = TerminologyService(config_root=tmp_path / "config" / "terminology", reports_root=reports_root)

    service.apply_to_text("ISU IS-U", "confluence", source_ref="known.md")
    assert not (reports_root / "terminology_candidates.csv").exists()
