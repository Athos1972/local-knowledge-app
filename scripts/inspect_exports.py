#!/usr/bin/env python3

from pathlib import Path
from collections import Counter, defaultdict
import argparse
import json


def analyze(root: Path, sample_per_ext=5):
    ext_counter = Counter()
    dir_counter = Counter()
    samples = defaultdict(list)

    total_files = 0

    for p in root.rglob("*"):
        if not p.is_file():
            continue

        total_files += 1

        ext = p.suffix.lower()
        ext_counter[ext] += 1

        rel = p.relative_to(root)
        dir_counter[str(rel.parent)] += 1

        if len(samples[ext]) < sample_per_ext:
            samples[ext].append(str(rel))

    return {
        "total_files": total_files,
        "extensions": ext_counter,
        "directories": dir_counter,
        "samples": samples,
    }


def print_tree(root: Path, depth=3, max_dirs=50):
    print("\nDirectory structure (limited depth):\n")

    count = 0

    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)

        if len(rel.parts) > depth:
            continue

        if p.is_dir():
            indent = "  " * (len(rel.parts) - 1)
            print(f"{indent}{p.name}/")

            count += 1
            if count > max_dirs:
                print("  ... truncated ...")
                break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        required=True,
        help="exports root directory",
    )
    parser.add_argument(
        "--json-out",
        help="optional json report",
    )

    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()

    print("\nAnalyzing:", root)

    data = analyze(root)

    print("\n==============================")
    print("EXPORT SUMMARY")
    print("==============================\n")

    print("Total files:", data["total_files"])

    print("\nTop extensions:\n")

    for ext, count in data["extensions"].most_common(20):
        label = ext if ext else "[no extension]"
        print(f"{label:12} {count:10}")

    print("\nTop directories:\n")

    for d, count in data["directories"].most_common(20):
        print(f"{d:50} {count}")

    print("\nSample files per extension:\n")

    for ext, files in data["samples"].items():
        label = ext if ext else "[no extension]"
        print(f"\n{label}")
        for f in files:
            print("  ", f)

    print_tree(root)

    if args.json_out:
        report = {
            "total_files": data["total_files"],
            "extensions": dict(data["extensions"]),
            "directories": dict(data["directories"]),
            "samples": dict(data["samples"]),
        }

        Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False)
        )

        print("\nJSON report written to:", args.json_out)


if __name__ == "__main__":
    main()