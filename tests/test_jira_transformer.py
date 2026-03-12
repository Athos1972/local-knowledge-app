from __future__ import annotations

from processing.jira.markdown_renderer import JiraMarkdownRenderer
from processing.jira.models import JiraRawIssue
from processing.jira.transformer import JiraTransformer


def test_transformer_and_renderer_generate_markdown_with_frontmatter() -> None:
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
        attachments=[{"name": "spec.pdf", "url": "https://jira.example.local/secure/attachment/1/spec.pdf"}],
    )

    transformed = JiraTransformer().transform(issue)
    markdown = JiraMarkdownRenderer().render(transformed)

    assert 'source_type: jira' in markdown
    assert 'jira_key: ABC-123' in markdown
    assert '# ABC-123: Test issue' in markdown
    assert '## Anhänge' in markdown
    assert '[spec.pdf](https://jira.example.local/secure/attachment/1/spec.pdf)' in markdown
