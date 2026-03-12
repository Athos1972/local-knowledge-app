from __future__ import annotations

from pathlib import Path
import sys
import types

from processing.jira.markdown_renderer import JiraMarkdownRenderer
from processing.jira.models import JiraRawIssue
from processing.jira.transformer import JiraTransformer


class _FakeResult:
    def __init__(self, text_content: str):
        self.text_content = text_content


class _FakeMarkItDown:
    def convert(self, _path: str):
        return _FakeResult("# attachment content")


def test_transformer_and_renderer_generate_markdown_with_frontmatter(tmp_path: Path, monkeypatch) -> None:
    attachment_file = tmp_path / "spec.pdf"
    attachment_file.write_text("dummy", encoding="utf-8")

    fake_module = types.SimpleNamespace(MarkItDown=_FakeMarkItDown)
    monkeypatch.setitem(sys.modules, "markitdown", fake_module)

    issue = JiraRawIssue(
        issue_id="1001",
        issue_key="ABC-123",
        project_key="ABC",
        summary="Test issue",
        description="<p>Beschreibung mit <strong>Text</strong>.</p>",
        source_ref="/tmp/metadata.json",
        source_url="https://jira.example.local/browse/ABC-123",
        status="In Progress",
        issue_type="Story",
        attachments=[{"name": "spec.pdf", "url": "https://jira.example.local/secure/attachment/1/spec.pdf", "local_path": str(attachment_file)}],
        attachment_paths=[str(attachment_file)],
    )

    transformed = JiraTransformer().transform(issue)
    markdown = JiraMarkdownRenderer().render(transformed)

    assert 'source_type: jira' in markdown
    assert 'jira_key: ABC-123' in markdown
    assert '# ABC-123: Test issue' in markdown
    assert '## Anhänge' in markdown
    assert '## Anhang-Inhalte (extrahiert)' in markdown
    assert '### spec.pdf' in markdown
    assert '# attachment content' in markdown
    assert '[spec.pdf](https://jira.example.local/secure/attachment/1/spec.pdf)' in markdown
