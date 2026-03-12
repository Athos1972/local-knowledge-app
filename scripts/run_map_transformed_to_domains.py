from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.domain_mapping import MapRunConfig, run_mapping


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map transformed scraping markdown from staging/transformed to domains/.")
    parser.add_argument("--transformed-root", type=Path, default=Path("staging/transformed"), help="Root containing transformed artifacts.")
    parser.add_argument("--domains-root", type=Path, default=Path("domains"), help="Target domains root.")
    parser.add_argument("--config", type=Path, default=Path("config/scraping_domain_mapping.toml"), help="Mapping configuration TOML.")
    parser.add_argument("--dry-run", action="store_true", help="Plan mapping without writing files.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing mapped files.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    stats = run_mapping(
        MapRunConfig(
            transformed_root=args.transformed_root,
            domains_root=args.domains_root,
            mapping_config_path=args.config,
            dry_run=args.dry_run,
            force=args.force,
        )
    )

    print("Domain mapping completed")
    print(f"- Seen: {stats.seen}")
    print(f"- Mapped: {stats.mapped}")
    print(f"- Skipped: {stats.skipped}")
    print(f"- Failed: {stats.failed}")


if __name__ == "__main__":
    main()
