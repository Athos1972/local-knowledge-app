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
    env["LOG_DIR"] = str(tmp_path / "logs")

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
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["PIPELINE_DISABLE_TEE"] = "1"
    cmd = ["bash", "pipeline.sh", "--only", "transform-documents"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0
    log_files = sorted((tmp_path / "logs").glob("run_pipeline_*.log"))
    assert log_files
    log_content = log_files[-1].read_text(encoding="utf-8")
    assert "Only step: transform-documents" in log_content


def test_run_transform_documents_cli_processes_jira_attachments_without_documents_root(tmp_path: Path) -> None:
    data_root = tmp_path / "local-knowledge-data"
    jira_attachment = data_root / "exports" / "jira" / "jira" / "inst-a" / "projects" / "attachments" / "ABC-123" / "spec.pdf"
    jira_attachment.parent.mkdir(parents=True)
    jira_attachment.write_text("dummy pdf bytes", encoding="utf-8")

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
    env["LOG_DIR"] = str(tmp_path / "logs")

    cmd = [
        sys.executable,
        "scripts/run_transform_documents.py",
        "--run-id",
        "documents-jira-attachment-run",
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr

    staging_files = list((data_root / "staging" / "documents").rglob("*.md"))
    assert len(staging_files) == 1

    content = staging_files[0].read_text(encoding="utf-8")
    assert "source_system: jira" in content
    assert "source_collection: ABC-123" in content
    assert "original_path: jira/inst-a/projects/attachments/ABC-123/spec.pdf" in content
    assert "parent_source_type: jira" in content
    assert "parent_key: ABC-123" in content


def test_run_transform_documents_cli_prefers_documents_root_over_duplicate_jira_attachment(tmp_path: Path) -> None:
    data_root = tmp_path / "local-knowledge-data"
    source_bytes = "same content"

    documents_file = data_root / "exports" / "documents" / "sharepoint" / "team-a" / "projektmanagement" / "spec.pdf"
    jira_attachment = data_root / "exports" / "jira" / "jira" / "inst-a" / "projects" / "attachments" / "WGS4H-123" / "spec.pdf"
    for file_path in (documents_file, jira_attachment):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source_bytes, encoding="utf-8")

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
    env["LOG_DIR"] = str(tmp_path / "logs")

    cmd = [sys.executable, "scripts/run_transform_documents.py", "--run-id", "documents-dedupe-prefer-documents"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr

    staging_files = list((data_root / "staging" / "documents").rglob("*.md"))
    assert len(staging_files) == 1
    content = staging_files[0].read_text(encoding="utf-8")
    assert "source_system: sharepoint" in content
    assert "original_path: sharepoint/team-a/projektmanagement/spec.pdf" in content
    assert "aliases:" in content

    manifest_path = data_root / "system" / "documents_transform" / "latest_transform_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents_seen"] == 2
    assert manifest["documents_processed"] == 1
    assert manifest["documents_skipped"] == 1
    assert any(record["status"].startswith("skipped_duplicate_of:") for record in manifest["records"])


def test_run_transform_documents_cli_deduplicates_same_content_across_non_document_sources(tmp_path: Path) -> None:
    data_root = tmp_path / "local-knowledge-data"
    source_bytes = "same content from other sources"

    jira_attachment = data_root / "exports" / "jira" / "jira" / "inst-a" / "projects" / "attachments" / "SKV-1572" / "mail.pdf"
    inbox_file = data_root / "inbox" / "2026-03" / "mail.pdf"
    for file_path in (jira_attachment, inbox_file):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source_bytes, encoding="utf-8")

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
    env["LOG_DIR"] = str(tmp_path / "logs")

    cmd = [sys.executable, "scripts/run_transform_documents.py", "--run-id", "documents-dedupe-global"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr

    staging_files = list((data_root / "staging" / "documents").rglob("*.md"))
    assert len(staging_files) == 1
    content = staging_files[0].read_text(encoding="utf-8")
    assert "source_system: jira" in content
    assert "original_path: jira/inst-a/projects/attachments/SKV-1572/mail.pdf" in content
