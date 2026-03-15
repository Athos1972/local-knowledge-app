from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_run_transform_jira_cli_creates_output(tmp_path: Path) -> None:
    input_root = tmp_path / "exports" / "jira"
    issue_dir = input_root / "jira" / "inst-a" / "projects" / "by-id" / "1002"
    issue_dir.mkdir(parents=True)
    (issue_dir / "content.storage.json").write_text(
        '{"id":"1002","key":"ABC-321","fields":{"summary":"CLI issue","project":{"key":"ABC"},"description":"<p>From CLI</p>"}}',
        encoding="utf-8",
    )

    output_root = tmp_path / "staging" / "jira"
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    cmd = [
        sys.executable,
        "scripts/run_transform_jira.py",
        "--input-root",
        str(input_root),
        "--output-root",
        str(output_root),
        "--run-id",
        "jira-test-run",
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    output_file = output_root / "abc" / "ABC-321__cli-issue.md"
    assert output_file.exists()


def test_pipeline_help_lists_jira_step_now_that_script_exists() -> None:
    cmd = ["bash", "pipeline.sh", "--help"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)

    assert result.returncode == 0
    assert "transform-jira" in result.stdout


def test_main_finalizes_terminology_report_once(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_jira as module
    from processing.jira.models import JiraRawIssue

    class DummyLoader:
        def __init__(self, _input_root: Path) -> None:
            pass

        def load_issues(self, project_filter: str | None = None):
            yield JiraRawIssue(
                issue_id="1",
                issue_key="ABC-1",
                project_key="ABC",
                summary="Issue 1",
                description="A" * 50,
                source_ref="issue-1.json",
                source_url="https://example.invalid/1",
                labels=[],
                components=[],
                fix_versions=[],
                attachments=[],
                attachment_paths=[],
            )

    class DummyTransformer:
        instances: list["DummyTransformer"] = []

        def __init__(self) -> None:
            self.transform_calls = 0
            self.finalize_calls = 0
            DummyTransformer.instances.append(self)

        def transform(self, issue):  # noqa: ANN001
            self.transform_calls += 1
            from processing.jira.models import JiraTransformedIssue

            return JiraTransformedIssue(
                issue_id=issue.issue_id,
                issue_key=issue.issue_key,
                project_key=issue.project_key,
                summary=issue.summary,
                body_markdown=f"# {issue.issue_key}: {issue.summary}\n\n{issue.description}",
                source_ref=issue.source_ref,
                source_url=issue.source_url,
                labels=[],
                components=[],
                fix_versions=[],
                attachments=[],
                transform_warnings=[],
                content_hash="hash",
            )

        def finalize_terminology_report(self) -> Path:
            self.finalize_calls += 1
            report_path = tmp_path / "reports" / "terminology_candidates.csv"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("source_type,term,count\njira,ALPHA,1\n", encoding="utf-8")
            return report_path

    monkeypatch.setattr(module, "JiraExportLoader", DummyLoader)
    monkeypatch.setattr(module, "JiraTransformer", DummyTransformer)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-jira-test")

    input_root = tmp_path / "exports" / "jira"
    input_root.mkdir(parents=True, exist_ok=True)
    output_root = tmp_path / "staging" / "jira"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_transform_jira.py",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--run-id",
            "run-jira-test",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    assert DummyTransformer.instances
    transformer = DummyTransformer.instances[0]
    assert transformer.transform_calls == 1
    assert transformer.finalize_calls == 1
