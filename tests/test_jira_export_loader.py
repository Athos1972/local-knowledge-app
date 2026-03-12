from __future__ import annotations

from pathlib import Path

from sources.jira_export.jira_export_loader import JiraExportLoader


def test_loads_issues_from_content_storage_in_nested_jira_layout(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    issue_dir = root / "jira" / "inst-a" / "projects" / "by-id" / "1001"
    issue_dir.mkdir(parents=True)

    (issue_dir / "content.storage.json").write_text(
        '{"id":"1001","key":"ABC-123","fields":{"summary":"Issue Summary","project":{"key":"ABC"},"status":{"name":"Done"},"description":"<p>Hello</p>"}}',
        encoding="utf-8",
    )

    issues = list(JiraExportLoader(root).load_issues())
    assert len(issues) == 1
    assert issues[0].issue_key == "ABC-123"
    assert issues[0].project_key == "ABC"
    assert issues[0].status == "Done"


def test_intermediate_jira_folder_is_optional_for_discovery(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    issue_dir = root / "inst-a" / "projects" / "by-id" / "1002"
    issue_dir.mkdir(parents=True)
    (issue_dir / "content.storage.json").write_text('{"id":"1002","key":"ABC-124"}', encoding="utf-8")

    issues = list(JiraExportLoader(root).load_issues())
    assert len(issues) == 1
    assert issues[0].issue_key == "ABC-124"


def test_missing_optional_fields_do_not_crash(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    issue_dir = root / "jira" / "inst-a" / "projects" / "by-id" / "1003"
    issue_dir.mkdir(parents=True)

    (issue_dir / "content.storage.json").write_text('{"id":"1003"}', encoding="utf-8")

    issues = list(JiraExportLoader(root).load_issues())
    assert len(issues) == 1
    assert issues[0].issue_id == "1003"
    assert issues[0].issue_key == "1003"
    assert issues[0].project_key == "unknown"
    assert issues[0].summary == "Ohne Titel"
    assert issues[0].labels == []
    assert issues[0].description == ""


def test_resolves_project_attachment_paths_by_issue_key(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    issue_dir = root / "jira" / "inst-a" / "projects" / "by-id" / "1004"
    attachment_dir = root / "jira" / "inst-a" / "projects" / "attachments" / "ABC-125"
    issue_dir.mkdir(parents=True)
    attachment_dir.mkdir(parents=True)

    attachment_file = attachment_dir / "spec.pdf"
    attachment_file.write_text("dummy", encoding="utf-8")

    (issue_dir / "content.storage.json").write_text(
        '{"id":"1004","key":"ABC-125","fields":{"summary":"Issue with attachment","project":{"key":"ABC"},"attachment":[{"filename":"spec.pdf"}]}}',
        encoding="utf-8",
    )

    issues = list(JiraExportLoader(root).load_issues())
    assert len(issues) == 1
    assert issues[0].attachment_paths == [str(attachment_file.resolve())]
    assert issues[0].attachments[0]["local_path"] == str(attachment_file.resolve())


def test_ignores_irrelevant_files_and_invalid_locations(tmp_path: Path) -> None:
    root = tmp_path / "exports" / "jira"
    (root / "README.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("not an issue", encoding="utf-8")

    invalid_dir = root / "jira" / "inst-a" / "projects" / "tickets" / "ABC-126"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "content.storage.json").write_text('{"id":"1005","key":"ABC-126"}', encoding="utf-8")
    (invalid_dir / ".DS_Store").write_text("x", encoding="utf-8")

    issues = list(JiraExportLoader(root).load_issues())
    assert issues == []
