from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_run_transform_confluence_skips_log_year_titles(tmp_path: Path) -> None:
    input_root = tmp_path / "exports" / "confluence"
    page_dir = input_root / "inst-a" / "spaces" / "DOC" / "by-id" / "123"
    page_dir.mkdir(parents=True)
    (page_dir / "metadata.json").write_text(
        json.dumps({"id": "123", "title": "Log 2024 Deployment", "space_key": "DOC"}),
        encoding="utf-8",
    )
    (page_dir / "content.storage.xml").write_text("<p>Soll ignoriert werden</p>", encoding="utf-8")

    output_root = tmp_path / "staging" / "confluence"
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    cmd = [
        sys.executable,
        "scripts/run_transform_confluence.py",
        "--input-root",
        str(input_root),
        "--output-root",
        str(output_root),
        "--run-id",
        "confluence-test-run",
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not output_root.exists() or not any(output_root.rglob("*.md"))
