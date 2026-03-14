from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_run_transform_documents_cli_creates_staging_and_publish_output(tmp_path: Path) -> None:
    input_root = tmp_path / "exports" / "documents"
    source_file = input_root / "sharepoint" / "team-a" / "projektmanagement" / "plan.pdf"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("dummy pdf bytes", encoding="utf-8")

    output_root = tmp_path / "staging" / "documents"
    publish_root = tmp_path / "ingest" / "domains"

    fake_module_dir = tmp_path / "fake_markitdown"
    fake_module_dir.mkdir()
    (fake_module_dir / "markitdown.py").write_text(
        """
class _Converted:
    text_content = "# Converted from fake markitdown"


class MarkItDown:
    def convert(self, _path: str):
        return _Converted()
""".strip(),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(fake_module_dir)
    env["HOME"] = str(tmp_path)

    cmd = [
        sys.executable,
        "scripts/run_transform_documents.py",
        "--input-root",
        str(input_root),
        "--output-root",
        str(output_root),
        "--publish-root",
        str(publish_root),
        "--run-id",
        "documents-test-run",
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr

    staging_files = list(output_root.rglob("*.md"))
    publish_files = list(publish_root.rglob("*.md"))
    assert len(staging_files) == 1
    assert len(publish_files) == 1

    content = staging_files[0].read_text(encoding="utf-8")
    assert "source_type: documents" in content
    assert "source_system: sharepoint" in content
    assert "domain: project_management" in content

    manifest_path = tmp_path / "local-knowledge-data" / "system" / "documents_transform" / "latest_transform_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents_processed"] == 1


def test_pipeline_help_lists_documents_step_and_skip_flag() -> None:
    cmd = ["bash", "pipeline.sh", "--help"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)

    assert result.returncode == 0
    assert "transform-documents" in result.stdout
    assert "--skip-documents" in result.stdout


def test_pipeline_only_transform_documents_works_without_input_dir(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    cmd = ["bash", "pipeline.sh", "--only", "transform-documents"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0
    assert "Only step: transform-documents" in result.stdout
