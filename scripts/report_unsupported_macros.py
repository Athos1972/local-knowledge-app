#!/usr/bin/env python3
"""Report für nicht unterstützte Confluence-Makros aus transformierten Markdown-Dateien."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.frontmatter_parser import FrontmatterParser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unsupported-Macro-Report für Confluence-Outputs")
    parser.add_argument("--root", type=Path, default=Path.home() / "local-knowledge-data" / "staging" / "confluence")
    parser.add_argument("--space", default=None, help="Optionaler Space-Key-Filter")
    parser.add_argument("--format", choices=["console", "csv", "json"], default="console")
    parser.add_argument("--output", default=None, help="Ausgabedatei für csv/json")
    return parser.parse_args()


def _load_rows(root: Path, space_filter: str | None) -> list[dict[str, Any]]:
    if not root.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.md")):
        if space_filter and path.parent.name.lower() != space_filter.lower():
            continue
        parsed = FrontmatterParser.parse(path.read_text(encoding="utf-8"))
        metadata = parsed.metadata
        if metadata.get("doc_type") != "confluence_page":
            continue
        unsupported = metadata.get("unsupported_macros")
        if not isinstance(unsupported, list) or not unsupported:
            continue

        page_id = str(metadata.get("page_id") or "")
        title = str(metadata.get("title") or path.stem)
        output_file = str(path)
        counts: dict[str, int] = {}
        for macro in unsupported:
            name = str(macro).strip() or "unknown_macro"
            counts[name] = counts.get(name, 0) + 1

        for macro_name, count in sorted(counts.items()):
            rows.append(
                {
                    "macro_name": macro_name,
                    "count": count,
                    "page_id": page_id,
                    "title": title,
                    "output_file": output_file,
                }
            )
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for row in rows:
        macro = row["macro_name"]
        totals[macro] = totals.get(macro, 0) + int(row["count"])
    return [
        {"macro_name": macro_name, "total_count": total}
        for macro_name, total in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def _render_console(aggregate: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    lines = ["Unsupported Macro Report", "========================", "", "Aggregiert nach Makroname:"]
    if not aggregate:
        lines.append("- Keine unsupported macros gefunden.")
        return "\n".join(lines)

    for item in aggregate:
        lines.append(f"- {item['macro_name']}: {item['total_count']}")

    lines.extend(["", "Dokument-Drilldown:"])
    for row in rows:
        lines.append(
            f"- {row['macro_name']} | count={row['count']} | page_id={row['page_id']} | title={row['title']} | output={row['output_file']}"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    rows = _load_rows(args.root.expanduser(), args.space)
    aggregate = _aggregate(rows)
    payload = {"aggregate": aggregate, "documents": rows}

    if args.format == "console":
        print(_render_console(aggregate, rows))
        return 0

    if args.output is None:
        raise SystemExit("--output ist für csv/json erforderlich")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "json":
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["macro_name", "count", "page_id", "title", "output_file"])
            writer.writeheader()
            writer.writerows(rows)
    print(f"Report geschrieben: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
