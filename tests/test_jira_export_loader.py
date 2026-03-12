from __future__ import annotations

from pathlib import Path

from sources.jira_export.jira_export_loader import JiraExportLoader


def test_loads_issues_from_projects_issues_structure(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    issue_dir = root / "inst-a" / "projects" / "ABC" / "issues" / "ABC-123"
    issue_dir.mkdir(parents=True)

    (issue_dir / "metadata.json").write_text(
        '{"id":"1001","key":"ABC-123","fields":{"summary":"Issue Summary","project":{"key":"ABC"},"status":{"name":"Done"},"description":"<p>Hello</p>"}}',
        encoding="utf-8",
    )

    issues = list(JiraExportLoader(root).load_issues())
    assert len(issues) == 1
    assert issues[0].issue_key == "ABC-123"
    assert issues[0].project_key == "ABC"
    assert issues[0].status == "Done"


def test_filters_out_metadata_not_inside_issue_collection(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    invalid_dir = root / "inst-a" / "projects" / "ABC" / "tickets" / "ABC-123"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "metadata.json").write_text('{"key":"ABC-123"}', encoding="utf-8")

    issues = list(JiraExportLoader(root).load_issues())
    assert issues == []
