from __future__ import annotations

from pathlib import Path

import pytest

from scripts import reset_pipeline_state as reset_mod
from scripts.reset_pipeline_state import DeletionTarget, ResetOptions, ResetPaths, collect_targets, delete_targets


@pytest.fixture(autouse=True)
def _stub_reset_logger(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(reset_mod, "get_logger", lambda *args, **kwargs: None)


def _paths(tmp_path: Path) -> ResetPaths:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    return ResetPaths(
        repo_root=repo_root,
        data_root=data_root,
        confluence_staging_root=data_root / "staging" / "confluence",
        scraping_staging_root=repo_root / "staging" / "transformed",
        jira_staging_root=data_root / "staging" / "jira",
        confluence_transform_manifest_root=data_root / "system" / "confluence_transform",
        jira_transform_manifest_root=data_root / "system" / "jira_transform",
        ingestion_manifest_root=data_root / "system" / "manifests",
        confluence_publish_manifest_root=data_root / "system" / "confluence_publish",
        domains_root=data_root / "domains",
        reports_root=repo_root / "reports",
        logs_root=repo_root / "logs",
        scripts_logs_root=repo_root / "scripts" / "logs",
        scipts_logs_root=repo_root / "scipts" / "logs",
        index_root=data_root / "index",
        processed_root=data_root / "processed",
        audit_root=data_root / "system" / "audit",
    )


def test_dry_run_collects_candidates(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    (paths.audit_root / "runs").mkdir(parents=True)
    (paths.audit_root / "pipeline_audit.sqlite").write_text("db", encoding="utf-8")
    (paths.audit_root / "runs" / "run_a.jsonl").write_text("{}", encoding="utf-8")

    (paths.processed_root / "chunks").mkdir(parents=True)
    (paths.processed_root / "chunks" / "chunk.jsonl").write_text("{}", encoding="utf-8")

    (paths.jira_staging_root / "inst-a").mkdir(parents=True)
    (paths.jira_staging_root / "inst-a" / "issue.md").write_text("# jira", encoding="utf-8")
    paths.ingestion_manifest_root.mkdir(parents=True)
    (paths.ingestion_manifest_root / "latest_run_manifest.json").write_text("{}", encoding="utf-8")

    options = ResetOptions(
        execute=False,
        yes=False,
        keep_exports=False,
        scopes=("audit", "staging"),
    )

    targets, _ = collect_targets(paths, options)
    target_paths = {target.path for target in targets}

    assert (paths.audit_root / "pipeline_audit.sqlite").resolve() in target_paths
    assert (paths.audit_root / "runs" / "run_a.jsonl").resolve() in target_paths
    assert (paths.processed_root / "chunks" / "chunk.jsonl").resolve() in target_paths
    assert (paths.jira_staging_root / "inst-a" / "issue.md").resolve() in target_paths
    assert (paths.ingestion_manifest_root / "latest_run_manifest.json").resolve() in target_paths


def test_execute_deletes_only_within_allowed_roots(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    paths = _paths(tmp_path)
    monkeypatch.setattr(reset_mod, "get_logger", lambda *args, **kwargs: None)
    safe_file = paths.logs_root / "app.log"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text("log", encoding="utf-8")

    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    deleted, warnings = delete_targets(
        targets=[
            DeletionTarget(category="logs", path=safe_file.resolve(), size_bytes=3, reason="log"),
            DeletionTarget(category="logs", path=outside.resolve(), size_bytes=2, reason="outside"),
        ],
        allowed_roots=[paths.logs_root],
    )

    assert deleted == 1
    assert not safe_file.exists()
    assert outside.exists()
    assert any("outside allowed roots" in warning for warning in warnings)


def test_idempotent_double_execute(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    (paths.index_root).mkdir(parents=True)
    target = paths.index_root / "vector_index.sqlite"
    target.write_text("index", encoding="utf-8")

    options = ResetOptions(
        execute=True,
        yes=True,
        keep_exports=False,
        scopes=("index",),
    )
    targets, _ = collect_targets(paths, options)
    deleted_first, warnings_first = delete_targets(targets, allowed_roots=[paths.index_root])

    targets_second, _ = collect_targets(paths, options)
    deleted_second, warnings_second = delete_targets(targets_second, allowed_roots=[paths.index_root])

    assert deleted_first == 1
    assert deleted_second == 0
    assert not warnings_first
    assert not warnings_second


def test_execute_prunes_empty_staging_directories(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    jira_leaf = paths.scraping_staging_root / "jira" / "project-a" / "board-1"
    jira_leaf.mkdir(parents=True)
    (jira_leaf / "issue-1.md").write_text("x", encoding="utf-8")

    options = ResetOptions(
        execute=True,
        yes=True,
        keep_exports=False,
        scopes=("staging",),
    )

    targets, _ = collect_targets(paths, options)
    deleted, warnings = delete_targets(targets, allowed_roots=[paths.scraping_staging_root])

    assert deleted == 1
    assert not warnings
    assert not (paths.scraping_staging_root / "jira").exists()
    assert paths.scraping_staging_root.exists()


def test_execute_prunes_empty_jira_staging_directories(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    jira_leaf = paths.jira_staging_root / "instance-a" / "project-x"
    jira_leaf.mkdir(parents=True)
    (jira_leaf / "issue-2.md").write_text("x", encoding="utf-8")

    options = ResetOptions(
        execute=True,
        yes=True,
        keep_exports=False,
        scopes=("staging",),
    )

    targets, _ = collect_targets(paths, options)
    deleted, warnings = delete_targets(targets, allowed_roots=[paths.jira_staging_root])

    assert deleted == 1
    assert not warnings
    assert not (paths.jira_staging_root / "instance-a").exists()
    assert paths.jira_staging_root.exists()


def test_execute_prunes_empty_ingestion_manifest_directories(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manifests_leaf = paths.ingestion_manifest_root / "runs" / "2024-01"
    manifests_leaf.mkdir(parents=True)
    (manifests_leaf / "run_1.json").write_text("{}", encoding="utf-8")

    options = ResetOptions(
        execute=True,
        yes=True,
        keep_exports=False,
        scopes=("staging",),
    )

    targets, _ = collect_targets(paths, options)
    deleted, warnings = delete_targets(targets, allowed_roots=[paths.ingestion_manifest_root])

    assert deleted == 1
    assert not warnings
    assert not (paths.ingestion_manifest_root / "runs").exists()
    assert paths.ingestion_manifest_root.exists()


def test_logs_scope_includes_repo_and_script_log_directories(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    repo_log = paths.logs_root / "app.log"
    script_log = paths.scripts_logs_root / "job.log"
    scipts_log = paths.scipts_logs_root / "legacy.log"

    repo_log.parent.mkdir(parents=True)
    script_log.parent.mkdir(parents=True)
    scipts_log.parent.mkdir(parents=True)

    repo_log.write_text("a", encoding="utf-8")
    script_log.write_text("b", encoding="utf-8")
    scipts_log.write_text("c", encoding="utf-8")

    options = ResetOptions(
        execute=False,
        yes=False,
        keep_exports=False,
        scopes=("logs",),
    )

    targets, _ = collect_targets(paths, options)
    target_paths = {target.path for target in targets}

    assert repo_log.resolve() in target_paths
    assert script_log.resolve() in target_paths
    assert scipts_log.resolve() in target_paths
