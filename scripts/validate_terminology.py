#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.terminology.validator import TerminologyValidator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate terminology YAML configuration")
    parser.add_argument("--config-dir", type=Path, default=Path("config/terminology"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()

    result = TerminologyValidator(args.config_dir).validate()
    if args.format == "json":
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Errors: {len(result.errors)} | Warnings: {len(result.warnings)}")
        for issue in result.errors:
            print(f"ERROR [{issue.code}] {issue.path}: {issue.message}")
        for issue in result.warnings:
            print(f"WARN  [{issue.code}] {issue.path}: {issue.message}")
        for message in result.info:
            print(f"INFO  {message}")

    if result.errors:
        return 1
    if args.strict and result.warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
