from __future__ import annotations

import json
from pathlib import Path
from urllib import error

from processing.anythingllm_ingest import (
    AnythingLLMState,
    AnythingLLMFileStateRecord,
    AnythingLLMIngestManifest,
    AnythingLLMIngestConfig,
    AnythingLLMClient,
    _build_multipart_upload_request,
    _is_non_transient_api_drift_error,
    format_duration_human,
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
        run_duration_human="1s",
    )
    payload = json.loads(manifest.to_json())
    assert payload["files_scanned"] == 3
    assert payload["files_uploaded"] == 2
    assert payload["bytes_uploaded"] == 80
    assert payload["run_duration_human"] == "1s"


def test_format_duration_human() -> None:
    assert format_duration_human(0.4) == "0s"
    assert format_duration_human(61.2) == "1m 1s"
    assert format_duration_human(3661) == "1h 1m 1s"


def test_multipart_builder_uses_configured_field_names(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.md"
    file_path.write_text("hello", encoding="utf-8")

    content_type, body = _build_multipart_upload_request(
        file_path=file_path,
        file_field_name="file",
        folder_field_name="folderName",
        folder_value="custom-documents",
    )

    assert content_type.startswith("multipart/form-data; boundary=")
    text = body.decode("utf-8", errors="replace")
    assert 'name="file"; filename="sample.md"' in text
    assert 'name="folderName"' in text
    assert "custom-documents" in text
    boundary = content_type.split("boundary=", 1)[1]
    assert body.endswith(f"--{boundary}--\r\n".encode("utf-8"))


def test_non_transient_error_marker_detection() -> None:
    assert _is_non_transient_api_drift_error('{"error": "Invalid file upload. Unexpected field"}')
    assert not _is_non_transient_api_drift_error('{"error": "temporary backend error"}')


def test_http_500_with_unexpected_field_does_not_retry(monkeypatch, tmp_path: Path) -> None:
    config = AnythingLLMIngestConfig(
        ingest_dir=tmp_path,
        data_root=tmp_path,
        workspace="ws",
        document_folder="custom-documents",
        allowed_extensions={".md"},
        max_file_size_bytes=1024,
        base_url="http://localhost:3001",
        api_key="token",
        upload_path="/api/v1/document/upload",
        upload_file_field="file",
        upload_folder_field="folder",
        workspace_attach_path_template="/api/v1/workspace/{workspace}/update-embeddings",
        timeout_seconds=2,
        max_retries=3,
        retry_backoff_seconds=0.01,
    )
    client = AnythingLLMClient(config)

    calls = {"count": 0}

    class DummyFp:
        def read(self) -> bytes:
            return b'{"success":false,"error":"Invalid file upload. Unexpected field"}'

        def close(self) -> None:
            return None

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        calls["count"] += 1
        raise error.HTTPError(req.full_url, 500, "Internal Server Error", hdrs=None, fp=DummyFp())

    monkeypatch.setattr("processing.anythingllm_ingest.request.urlopen", fake_urlopen)

    try:
        client._request(
            "/api/v1/document/upload",
            method="POST",
            body=b"x",
            request_context={"file_field": "file", "folder_field": "folder"},
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "nicht-transienter API-Fehler" in message
    else:
        raise AssertionError("RuntimeError expected")

    assert calls["count"] == 1





def test_embed_in_workspace_uses_adds_with_uploaded_location(tmp_path: Path) -> None:
    config = AnythingLLMIngestConfig(
        ingest_dir=tmp_path,
        data_root=tmp_path,
        workspace="ws",
        document_folder="custom-documents",
        allowed_extensions={".md"},
        max_file_size_bytes=1024,
        base_url="http://localhost:3001",
        api_key="token",
        upload_path="/api/v1/document/upload",
        upload_file_field="file",
        upload_folder_field="folder",
        workspace_attach_path_template="/api/v1/workspace/{workspace}/update-embeddings",
        timeout_seconds=2,
        max_retries=2,
        retry_backoff_seconds=0.01,
    )
    client = AnythingLLMClient(config)

    captured: dict[str, object] = {}

    def fake_request(path: str, *, method: str, body=None, json_body=None, headers=None, request_context=None):
        captured["path"] = path
        captured["method"] = method
        captured["json_body"] = json_body
        captured["request_context"] = request_context
        return {}

    client._request = fake_request  # type: ignore[method-assign]
    client.embed_in_workspace(
        workspace="WSTW",
        document_location="custom-documents/name-von-anythingllm.json",
        force_reembed=False,
    )

    assert captured["path"] == "/api/v1/workspace/ws/update-embeddings"
    assert captured["method"] == "POST"
    assert captured["json_body"] == {"adds": ["custom-documents/name-von-anythingllm.json"]}


def test_run_lifecycle_finishes_failed_on_unhandled_exception(monkeypatch, tmp_path: Path) -> None:
    from processing import anythingllm_ingest as mod

    config = mod.AnythingLLMIngestConfig(
        ingest_dir=tmp_path,
        data_root=tmp_path,
        workspace="ws",
        document_folder="docs",
        allowed_extensions={".md"},
        max_file_size_bytes=1024,
        base_url="http://localhost:3001",
        api_key="token",
        upload_path="/api/v1/document/upload",
        upload_file_field="file",
        upload_folder_field="folder",
        workspace_attach_path_template="/api/v1/workspace/{workspace}/update-embeddings",
        timeout_seconds=2,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    class DummyRunContext:
        run_id = "run-ctx"

        def __init__(self):
            self.status = None

        def finish(self, status: str = "finished") -> None:
            self.status = status

    class DummyAudit:
        def stage(self, **kwargs):  # noqa: ANN003
            class Ctx:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return Ctx()

    dummy_context = DummyRunContext()
    monkeypatch.setattr(mod, "build_audit_components", lambda **kwargs: (dummy_context, DummyAudit()))
    monkeypatch.setattr(mod, "build_delta_plan", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    try:
        mod.run_anythingllm_ingest(config)
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("RuntimeError expected")

    assert dummy_context.status == "failed"
