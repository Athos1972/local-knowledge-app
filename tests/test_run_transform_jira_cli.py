from __future__ import annotations

import json
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
    config_path = tmp_path / "app.toml"
    config_path.write_text(
        """
[terminology]
reports_dir = "{reports_dir}"
""".strip().format(reports_dir=str(tmp_path / "reports")),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["APP_CONFIG_FILE"] = str(config_path)

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


def test_main_logs_progress_and_persists_changed_count(monkeypatch, tmp_path: Path) -> None:
    from scripts import run_transform_jira as module
    from processing.jira.models import JiraRawIssue, JiraTransformedIssue

    class DummyLogger:
        def __init__(self) -> None:
            self.info_messages: list[str] = []
            self.debug_messages: list[str] = []
            self.warning_messages: list[str] = []

        def info(self, message, *args) -> None:  # noqa: ANN001
            self.info_messages.append(message % args if args else message)

        def debug(self, message, *args) -> None:  # noqa: ANN001
            self.debug_messages.append(message % args if args else message)

        def warning(self, message, *args) -> None:  # noqa: ANN001
            self.warning_messages.append(message % args if args else message)

        def exception(self, message, *args) -> None:  # noqa: ANN001
            self.warning_messages.append(message % args if args else message)

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
                attachments=[{"name": "spec.pdf", "local_path": "/tmp/spec.pdf"}],
                attachment_paths=["/tmp/spec.pdf"],
            )
            yield JiraRawIssue(
                issue_id="2",
                issue_key="ABC-2",
                project_key="ABC",
                summary="Issue 2",
                description="B" * 50,
                source_ref="issue-2.json",
                source_url="https://example.invalid/2",
                labels=[],
                components=[],
                fix_versions=[],
                attachments=[],
                attachment_paths=[],
            )

    class DummyTransformer:
        def finalize_terminology_report(self) -> Path:
            report_path = tmp_path / "reports" / "terminology_candidates.csv"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("source_type,term,count\njira,ALPHA,1\n", encoding="utf-8")
            return report_path

        def transform(self, issue):  # noqa: ANN001
            return JiraTransformedIssue(
                issue_id=issue.issue_id,
                issue_key=issue.issue_key,
                project_key=issue.project_key,
                summary=issue.summary,
                body_markdown=f"# {issue.issue_key}: {issue.summary}\n\nBody",
                source_ref=issue.source_ref,
                source_url=issue.source_url,
                labels=[],
                components=[],
                fix_versions=[],
                attachments=[],
                transform_warnings=[],
                attachment_stats={
                    "total": len(issue.attachments),
                    "extracted": len(issue.attachments),
                    "failed": 0,
                    "suffix_counts": {".pdf": len(issue.attachments)} if issue.attachments else {},
                    "warning_counts": {},
                    "duration_by_suffix_ms": {".pdf": 12.5} if issue.attachments else {},
                },
                content_hash=f"hash-{issue.issue_key}",
            )

    logger = DummyLogger()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(module, "JiraExportLoader", DummyLoader)
    monkeypatch.setattr(module, "JiraTransformer", DummyTransformer)
    monkeypatch.setattr(module, "get_logger", lambda *_args, **_kwargs: logger)
    monkeypatch.setattr(module, "generate_transform_run_id", lambda: "run-jira-progress")
    monkeypatch.setattr(module, "PROGRESS_LOG_EVERY_ISSUES", 1)
    monkeypatch.setattr(module, "CHECKPOINT_SAVE_EVERY_ISSUES", 1)

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
            "run-jira-progress",
            "--full-refresh",
        ],
    )

    rc = module.main()

    assert rc == 0
    assert any("JIRA progress." in message for message in logger.info_messages)
    assert any("JIRA attachment summary." in message for message in (logger.info_messages + logger.debug_messages))

    manifest = json.loads((tmp_path / "local-knowledge-data" / "system" / "jira_transform" / "latest_transform_manifest.json").read_text(encoding="utf-8"))
    state = json.loads((tmp_path / "local-knowledge-data" / "system" / "jira_transform" / "latest_transform_state.json").read_text(encoding="utf-8"))

    assert manifest["issues_changed"] == 2
    assert state["summary"]["issues_changed"] == 2
    assert state["summary"]["issues_processed"] == 2
