#!/usr/bin/env python3
"""CLI-Step: Delta-Ingest aus ingest/ nach AnythingLLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.anythingllm_ingest import AnythingLLMIngestConfig, run_anythingllm_ingest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delta ingest from ingest/ to AnythingLLM workspace")
    parser.add_argument("--ingest-dir", type=Path, default=None, help="Override ingest root directory")
    parser.add_argument("--dry-run", action="store_true", help="Plan delta and stats without API calls")
    parser.add_argument("--force-reupload", action="store_true", help="Force upload all candidate files")
    parser.add_argument("--force-reembed", action="store_true", help="Force re-embedding for processed files")
    parser.add_argument("--run-id", default=None, help="Optional external run id")
    parser.add_argument("--source-instance", default="anythingllm", help="Audit source_instance value")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AnythingLLMIngestConfig.from_env_and_args(
        ingest_dir=args.ingest_dir,
        dry_run=args.dry_run,
        force_reupload=args.force_reupload,
        force_reembed=args.force_reembed,
        run_id=args.run_id,
        source_instance=args.source_instance,
    )
    exit_code, manifest = run_anythingllm_ingest(config)
    print("AnythingLLM ingest finished")
    print(f"- run_id: {manifest.run_id}")
    print(f"- scanned: {manifest.files_scanned}")
    print(f"- candidate: {manifest.files_candidate}")
    print(f"- uploaded: {manifest.files_uploaded}")
    print(f"- embedded: {manifest.files_embedded}")
    print(f"- skipped: {manifest.files_skipped}")
    print(f"- failed: {manifest.files_failed}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
