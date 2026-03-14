#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json

SUPPORTED_EXTS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".csv", ".json", ".xml", ".epub",
}


def count_files(root: Path) -> tuple[Counter, int]:
    counter = Counter()
    total = 0

    for path in root.rglob("*"):
        if path.is_file():
            total += 1
            counter[path.suffix.lower()] += 1

    return counter, total


def count_supported(root: Path) -> int:
    return sum(
        1
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def count_staging_outputs(staging_root: Path) -> dict:
    md_count = 0
    meta_count = 0
    manifest_count = 0

    for p in staging_root.rglob("*"):
        if not p.is_file():
            continue

        name = p.name.lower()

        if name.endswith(".meta.json"):
            meta_count += 1
        elif name.endswith(".md"):
            md_count += 1

        if name.startswith("manifest_") and name.endswith(".json"):
            manifest_count += 1
        elif name == "manifest.latest.json":
            manifest_count += 1

    return {
        "staging_md": md_count,
        "staging_meta_json": meta_count,
        "staging_manifests": manifest_count,
    }


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{(numerator / denominator) * 100:.2f}%"


def print_top_extensions(counter: Counter, limit: int = 20) -> None:
    print("\nTop Extensions:")
    for ext, count in counter.most_common(limit):
        label = ext if ext else "[no extension]"
        marker = "  <-- supported" if ext in SUPPORTED_EXTS else ""
        print(f"  {label:15s} {count:10d}{marker}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quick analyzer for export/staging coverage."
    )
    parser.add_argument(
        "--export-root",
        type=Path,
        required=True,
        help="Path to export root, e.g. data/exports/scraping",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        required=True,
        help="Path to staging root, e.g. data/staging/transformed",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to write JSON report",
    )
    args = parser.parse_args()

    export_root = args.export_root.expanduser().resolve()
    staging_root = args.staging_root.expanduser().resolve()

    export_exts, export_total = count_files(export_root)
    supported_exports = count_supported(export_root)
    staging_stats = count_staging_outputs(staging_root)

    staging_md = staging_stats["staging_md"]
    staging_meta = staging_stats["staging_meta_json"]

    report = {
        "export_root": str(export_root),
        "staging_root": str(staging_root),
        "export_total_files": export_total,
        "supported_export_files": supported_exports,
        "staging_md_files": staging_md,
        "staging_meta_json_files": staging_meta,
        "staging_manifests": staging_stats["staging_manifests"],
        "coverage_supported_to_md": None if supported_exports == 0 else round(staging_md / supported_exports, 4),
        "md_meta_gap": staging_md - staging_meta,
        "top_extensions": [
            {
                "extension": ext or "[no extension]",
                "count": count,
                "supported": ext in SUPPORTED_EXTS,
            }
            for ext, count in export_exts.most_common(30)
        ],
    }

    print("=" * 72)
    print("LOCAL KNOWLEDGE COVERAGE ANALYZER")
    print("=" * 72)
    print(f"Export root              : {export_root}")
    print(f"Staging root             : {staging_root}")
    print(f"Export total files       : {export_total}")
    print(f"Supported export files   : {supported_exports}")
    print(f"Staging .md files        : {staging_md}")
    print(f"Staging .meta.json files : {staging_meta}")
    print(f"Staging manifests        : {staging_stats['staging_manifests']}")
    print(f"Coverage (.md/support)   : {pct(staging_md, supported_exports)}")
    print(f"MD vs META gap           : {staging_md - staging_meta}")

    if staging_md != staging_meta:
        print("WARNING: .md and .meta.json counts differ.")

    print_top_extensions(export_exts, limit=20)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON report written to   : {args.json_out}")

    print("\nInterpretation:")
    print("- Relevant coverage is mainly: staging .md / supported export files")
    print("- A large gap between export_total and supported_export_files is normal")
    print("  when many images/assets/binary side-files are present.")
    print("- MD vs META gap should normally be 0 or very close to 0.")


if __name__ == "__main__":
    main()