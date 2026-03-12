from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.config import AppConfig
from pipelines.scraping_transform import TransformRunConfig, run_transform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transform files from exports/scraping into staging/transformed markdown artifacts.")
    parser.add_argument("--input-root", type=Path, default=None, help="Input root containing scraped files.")
    parser.add_argument("--output-root", type=Path, default=None, help="Output root for transformed artifacts.")
    parser.add_argument("--config", type=Path, help="Reserved for future config-based transforms.")
    parser.add_argument("--dry-run", action="store_true", help="Plan operations without writing files.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of supported files to process.")
    parser.add_argument("--force", action="store_true", help="Force rewrite even when changed-only would skip.")
    parser.add_argument("--changed-only", action="store_true", help="Only process files newer than existing artifacts.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_root_default = AppConfig.get_path(None, "scraping_transform", "input_root", default="exports/scraping")
    output_root_default = AppConfig.get_path(None, "scraping_transform", "output_root", default="staging/transformed")

    config = TransformRunConfig(
        input_root=(args.input_root.expanduser() if args.input_root else input_root_default),
        output_root=(args.output_root.expanduser() if args.output_root else output_root_default),
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
        changed_only=args.changed_only,
    )

    report = run_transform(config)
    print("Transform run completed")
    print(f"- Run ID: {report.run_id}")
    print(f"- Seen files: {report.total_seen}")
    print(f"- Supported files: {report.total_supported}")
    print(f"- Transformed: {report.transformed}")
    print(f"- Skipped: {report.skipped}")
    print(f"- Failed: {report.failed}")
    print(f"- Duration: {report.run_duration:.2f}s ({report.run_duration_human})")


if __name__ == "__main__":
    main()
