#!/usr/bin/env python3
"""CLI: Audit-Diagnose-Report für Pipeline-Runs erzeugen."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.audit.reporting import (  # noqa: E402
    AuditReportService,
    ReportFilters,
    export_drilldown_csv,
    export_drilldown_json,
    export_problem_documents_csv,
    render_console,
    render_markdown,
)
from processing.audit.repository import AuditRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit-Report für Ingestion/Index-Pipeline")
    parser.add_argument("--root", type=Path, default=Path.home() / "local-knowledge-data")
    parser.add_argument("--date", dest="report_date", default=None, help="Datum im Format YYYY-MM-DD (Default: heute)")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--source-type", default=None)
    parser.add_argument("--source-instance", default=None)
    parser.add_argument("--format", choices=["console", "markdown", "csv", "json"], default="console")
    parser.add_argument("--markdown-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--drilldown", action="store_true", help="Detaillierten Dokument-Drilldown exportieren")
    parser.add_argument("--only-problematic", action="store_true", help="Im Drilldown nur problematische Dokumente exportieren")
    parser.add_argument("--output", default=None, help="Ausgabepfad für Drilldown-CSV/JSON")
    parser.add_argument("--output-format", "--drilldown-format", dest="output_format", choices=["csv", "json"], default=None, help="Format für Drilldown-Ausgabe")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_date = date.fromisoformat(args.report_date) if args.report_date else date.today()

    repository = AuditRepository(args.root / "system" / "audit" / "pipeline_audit.sqlite")
    service = AuditReportService(repository)
    filters = ReportFilters(
        report_date=report_date,
        run_id=args.run_id,
        source_type=args.source_type,
        source_instance=args.source_instance,
        only_problematic=args.only_problematic,
    )
    report = service.build_report(filters)

    if args.format in {"csv", "json"}:
        args.drilldown = True
        args.output_format = args.format
    output = render_markdown(report) if args.format == "markdown" else render_console(report)
    if args.format in {"console", "markdown"}:
        print(output)

    if args.markdown_out:
        out_path = Path(args.markdown_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Markdown-Report geschrieben: {out_path}")

    if args.csv_out:
        csv_path = Path(args.csv_out)
        export_problem_documents_csv(report, csv_path)
        print(f"CSV geschrieben: {csv_path}")

    if args.drilldown:
        rows = service.build_drilldown(filters)
        drilldown_format = args.output_format or "csv"
        default_name = f"audit_drilldown_{args.run_id or report_date.isoformat()}.{drilldown_format}"
        output_path = Path(args.output or (Path("reports") / "audit" / default_name))
        if drilldown_format == "json":
            export_drilldown_json(rows, output_path)
        else:
            export_drilldown_csv(rows, output_path)
        print(f"Drilldown geschrieben: {output_path} ({len(rows)} Zeilen)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
