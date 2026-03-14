from __future__ import annotations

from pathlib import Path

from processing.documents.domain_mapper import DomainMapper


def test_domain_mapper_uses_first_matching_rule() -> None:
    mapper = DomainMapper.from_config(
        [
            {"match": "sharepoint/*/projektmanagement/**", "domain": "project_management"},
            {"match": "sharepoint/*/architektur/**", "domain": "architecture"},
        ],
        fallback_domain="misc_documents",
    )

    assert mapper.resolve_domain(Path("sharepoint/team-a/projektmanagement/plan.pdf")) == "project_management"
    assert mapper.resolve_domain(Path("sharepoint/team-a/architektur/adr.docx")) == "architecture"
    assert mapper.resolve_domain(Path("book/arisca/raw/chapter1.pdf")) == "misc_documents"
