from __future__ import annotations

from pathlib import Path
import sys
import types

from processing.image_analysis.models import DerivedFileArtifact, ImageAnalysisArtifactBundle, ImageAnalysisRef
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
    assert 'attachment_document_ids:' in markdown
    assert transformed.attachment_stats["total"] == 1
    assert transformed.attachment_stats["extracted"] == 1
    assert transformed.attachment_stats["suffix_counts"][".pdf"] == 1


def test_transformer_keeps_issue_running_when_attachment_is_missing(tmp_path: Path) -> None:
    issue = JiraRawIssue(
        issue_id="1002",
        issue_key="ABC-124",
        project_key="ABC",
        summary="Missing attachment issue",
        description="<p>Beschreibung.</p>",
        source_ref="/tmp/metadata.json",
        source_url="https://jira.example.local/browse/ABC-124",
        attachments=[{"name": "missing.docx", "local_path": str(tmp_path / "missing.docx")}],
        attachment_paths=[],
    )

    transformed = JiraTransformer().transform(issue)
    markdown = JiraMarkdownRenderer().render(transformed)

    assert '# ABC-124: Missing attachment issue' in markdown
    assert transformed.attachment_stats["total"] == 1
    assert transformed.attachment_stats["extracted"] == 0
    assert transformed.attachment_stats["failed"] >= 1
    assert transformed.attachment_stats["warning_counts"]["attachment_file_not_found"] == 1


def test_transformer_links_image_analysis_artifacts(tmp_path: Path, monkeypatch) -> None:
    image_file = tmp_path / "screen.png"
    image_file.write_bytes(b"png")

    def fake_analyze(self, image_path: Path, parent_context):  # noqa: ANN001
        return ImageAnalysisArtifactBundle(
            reference=ImageAnalysisRef(
                attachment_name=image_path.name,
                attachment_path=str(image_path),
                mime_type="image/png",
                sha256="hash123",
                image_kind="screenshot",
                summary="SAP-Screenshot mit Fehlermeldung",
                signals=["sap_gui", "error_message"],
                entities=["SAP"],
                ocr_provider="fake-ocr",
                vision_provider="fake-vision",
                derived_md_file="ABC-125__image__screen.md",
                derived_json_file="ABC-125__image__screen.json",
            ),
            markdown_artifact=DerivedFileArtifact(
                file_name="ABC-125__image__screen.md",
                media_type="text/markdown",
                content="---\ntitle: Bildanalyse\n---\n\n## Kurzbeschreibung\n\nSAP-Screenshot\n",
            ),
            json_artifact=DerivedFileArtifact(
                file_name="ABC-125__image__screen.json",
                media_type="application/json",
                content='{"summary":"SAP-Screenshot"}\n',
            ),
            embed_markdown="## Kurzbeschreibung\n\nSAP-Screenshot mit Fehlermeldung\n",
        )

    monkeypatch.setattr("processing.image_analysis.service.ImageAnalysisService.analyze", fake_analyze)

    issue = JiraRawIssue(
        issue_id="1003",
        issue_key="ABC-125",
        project_key="ABC",
        summary="Image attachment issue",
        description="<p>Beschreibung.</p>",
        source_ref="/tmp/metadata.json",
        source_url="https://jira.example.local/browse/ABC-125",
        attachments=[{"name": "screen.png", "local_path": str(image_file)}],
        attachment_paths=[str(image_file)],
    )

    transformed = JiraTransformer().transform(issue)
    markdown = JiraMarkdownRenderer().render(transformed)

    assert transformed.image_analysis_refs
    assert transformed.derived_artifacts
    assert "## Abgeleitete Bildanalysen" in transformed.body_markdown
    assert "[screen.png](ABC-125__image__screen.md)" in transformed.body_markdown
    assert "image_analysis_status: complete" in markdown
    assert "ABC-125__image__screen.md" in markdown
