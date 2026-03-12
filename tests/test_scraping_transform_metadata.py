from __future__ import annotations

from pathlib import Path

from pipelines.scraping_transform import _build_metadata_payload


def test_metadata_payload_contains_required_fields(tmp_path: Path) -> None:
    source = tmp_path / "sample.json"
    source.write_text('{"k":"v"}', encoding="utf-8")

    payload = _build_metadata_payload(
        run_id="run-1",
        source_path=source,
        input_root=tmp_path,
        transformer_name="markitdown",
        transformer_version="1.0.0",
        markdown="# X",
        base_metadata={"mime_type": "application/json"},
        warnings=["warn"],
        success=True,
        error=None,
    )

    assert payload["source_system"] == "scraping"
    assert payload["relative_source_path"] == "sample.json"
    assert payload["transformer"] == "markitdown"
    assert payload["markdown_char_count"] == 3
    assert payload["success"] is True
    assert payload["sha256"]
