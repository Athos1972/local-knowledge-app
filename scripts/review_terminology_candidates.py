#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.terminology.candidates import TerminologyCandidateReviewService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review/enrich terminology candidate CSV")
    parser.add_argument("--config-dir", type=Path, default=Path("config/terminology"))
    parser.add_argument("--candidates", type=Path, default=Path("reports/terminology_candidates.csv"))
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    rows = TerminologyCandidateReviewService(args.config_dir, args.candidates).enrich()
    print(f"Reviewed {len(rows)} candidate rows: {args.candidates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
