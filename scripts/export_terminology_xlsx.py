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
    parser = argparse.ArgumentParser(description="Export terminology YAML to XLSX")
    parser.add_argument("--config-dir", type=Path, default=Path("config/terminology"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--output", type=Path, default=Path("reports/terminology.xlsx"))
    parser.add_argument("--candidates", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    TerminologyExcelService(args.config_dir, args.reports_dir).export_xlsx(output=args.output, candidates_csv=args.candidates)
    print(f"XLSX export written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
