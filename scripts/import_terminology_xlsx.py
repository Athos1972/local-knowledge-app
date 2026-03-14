#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.terminology.excel import TerminologyExcelService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import terminology XLSX back into YAML")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, default=Path("config/terminology"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", action="store_true")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    result = TerminologyExcelService(args.config_dir, args.reports_dir).import_xlsx(
        input_path=args.input,
        dry_run=args.dry_run,
        backup=args.backup,
    )
    print(f"XLSX import processed: terms={result.terms} aliases={result.aliases} relations={result.relations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
