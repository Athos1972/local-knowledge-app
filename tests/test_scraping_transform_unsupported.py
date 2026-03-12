from __future__ import annotations

from pathlib import Path

import pytest

from pipelines.scraping_transform import TransformRunConfig, run_transform


def test_run_transform_reports_unsupported_files(tmp_path: Path) -> None:
    input_root = tmp_path / "exports"
    output_root = tmp_path / "staging"
    input_root.mkdir()
    (input_root / "note.txt").write_text("x", encoding="utf-8")

    report = run_transform(TransformRunConfig(input_root=input_root, output_root=output_root, dry_run=True))

    assert report.total_seen == 1
    assert report.total_supported == 0
    assert report.unsupported == 1
    assert report.skipped == 1
    assert report.records[0].status == "skipped"
    assert "unsupported extension" in report.records[0].warnings[0]


def test_run_transform_fail_on_unsupported(tmp_path: Path) -> None:
    input_root = tmp_path / "exports"
    output_root = tmp_path / "staging"
    input_root.mkdir()
    (input_root / "note.txt").write_text("x", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unsupported files encountered"):
        run_transform(
            TransformRunConfig(
                input_root=input_root,
                output_root=output_root,
                dry_run=True,
                fail_on_unsupported=True,
            )
        )
