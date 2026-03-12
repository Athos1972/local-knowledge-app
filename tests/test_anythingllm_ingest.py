from __future__ import annotations

import json
from pathlib import Path

from processing.anythingllm_ingest import (
    AnythingLLMState,
    AnythingLLMFileStateRecord,
    AnythingLLMIngestManifest,
    build_delta_plan,
    infer_top_level_group,
    is_allowed_extension,
)


def test_file_filter_and_delta_decision(tmp_path: Path) -> None:
    ingest = tmp_path / "ingest"
    (ingest / "confluence").mkdir(parents=True)
    (ingest / "jira").mkdir(parents=True)

    file_new = ingest / "confluence" / "new.md"
    file_new.write_text("hello", encoding="utf-8")
    file_changed = ingest / "jira" / "changed.txt"
    file_changed.write_text("new content", encoding="utf-8")
    file_unchanged = ingest / "jira" / "same.json"
    file_unchanged.write_text('{"x": 1}', encoding="utf-8")
    file_filtered = ingest / "jira" / "skip.pdf"
    file_filtered.write_text("binary?", encoding="utf-8")

    state = AnythingLLMState(
        files={
            "jira/changed.txt": AnythingLLMFileStateRecord(
                sha256="oldhash",
                size_bytes=1,
                uploaded_document="doc-a",
                updated_at="2026-01-01T00:00:00Z",
            ),
            "jira/same.json": AnythingLLMFileStateRecord(
                sha256="613fe5aa65343dbb1b9abe6abac6773f5c91bd60d3f2ffb7e2eae69e1db8b227",
                size_bytes=8,
                uploaded_document="doc-b",
                updated_at="2026-01-01T00:00:00Z",
            ),
        }
    )

    plan = build_delta_plan(ingest, {".md", ".txt", ".json"}, 1024 * 1024, state)
    actions = {entry.relative_path: entry.action for entry in plan}

    assert actions["confluence/new.md"] == "new"
    assert actions["jira/changed.txt"] == "changed"
    assert actions["jira/same.json"] == "unchanged"
    assert actions["jira/skip.pdf"] == "filtered"


def test_grouping_top_level_folder() -> None:
    assert infer_top_level_group("confluence/a/file.md") == "confluence"
    assert infer_top_level_group("jira/file.md") == "jira"
    assert infer_top_level_group("scraping/file.md") == "scraping"


def test_is_allowed_extension() -> None:
    assert is_allowed_extension(Path("a.md"), {".md", ".json"})
    assert not is_allowed_extension(Path("a.exe"), {".md", ".json"})


def test_manifest_stats_serialization() -> None:
    manifest = AnythingLLMIngestManifest(
        run_id="run-1",
        started_at="2026-03-01T00:00:00Z",
        files_scanned=3,
        files_candidate=2,
        files_new=1,
        files_changed=1,
        files_unchanged=1,
        files_uploaded=2,
        files_embedded=2,
        files_skipped=1,
        files_failed=0,
        bytes_total=100,
        bytes_uploaded=80,
        run_duration=1.23,
    )
    payload = json.loads(manifest.to_json())
    assert payload["files_scanned"] == 3
    assert payload["files_uploaded"] == 2
    assert payload["bytes_uploaded"] == 80
