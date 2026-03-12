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
