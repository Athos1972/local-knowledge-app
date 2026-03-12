#!/usr/bin/env python3
"""CLI für die Transformation lokal exportierter JIRA-Issues in Markdown."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.config import AppConfig
from common.logging_setup import get_logger
from common.time_utils import format_duration_human
from processing.audit import AuditStage, ReasonCode, build_audit_components
from processing.jira.markdown_renderer import JiraMarkdownRenderer
from processing.jira.transform_manifest import JiraTransformRecord, JiraTransformRunManifest, generate_transform_run_id
from processing.jira.transform_state import JiraTransformState, JiraTransformStateRecord
from processing.jira.transformer import JiraTransformer
from processing.jira.writer import JiraTransformWriter
from sources.document import stable_hash, utc_now_iso
from sources.jira_export.jira_export_loader import JiraExportLoader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JIRA export transform")
    parser.add_argument("--full-refresh", "--full", dest="full_refresh", action="store_true")
    parser.add_argument("--project", dest="project", default=None, help="Optionaler Project-Key-Filter")
    parser.add_argument("--input-root", dest="input_root", default=None)
    parser.add_argument("--output-root", dest="output_root", default=None)
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--source-instance", dest="source_instance", default="jira-export")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    data_root = Path.home() / "local-knowledge-data"
    default_input_root = data_root / "exports" / "jira"
    default_output_root = data_root / "staging" / "jira"

    input_root = Path(args.input_root).expanduser() if args.input_root else AppConfig.get_path(None, "jira_transform", "input_root", default=str(default_input_root))
    output_root = Path(args.output_root).expanduser() if args.output_root else AppConfig.get_path(None, "jira_transform", "output_root", default=str(default_output_root))

    if not input_root.exists():
        hint = "(CLI --input-root)" if args.input_root else "(config key [jira_transform].input_root in config/app.toml)"
        raise FileNotFoundError(f"JIRA input root not found: {input_root} {hint}")
    manifests_dir = AppConfig.get_path(None, "jira_transform", "manifests_dir", default=str(data_root / "system" / "jira_transform"))

    mode = "full" if args.full_refresh else "incremental"
    effective_run_id = args.run_id or generate_transform_run_id()
    manifest = JiraTransformRunManifest(run_id=effective_run_id, started_at=utc_now_iso(), mode=mode)
    logger = get_logger("run_transform_jira", run_id=manifest.run_id)
    started_perf = perf_counter()

    loader = JiraExportLoader(input_root)
    transformer = JiraTransformer()
    renderer = JiraMarkdownRenderer()
    writer = JiraTransformWriter(output_root)

    state_path = manifests_dir / "latest_transform_state.json"
    latest_manifest_path = manifests_dir / "latest_transform_manifest.json"
    run_manifest_path = manifests_dir / f"run_{manifest.run_id}.json"

    state = JiraTransformState.load(state_path)
    run_context, audit = build_audit_components(
        data_root=data_root,
        source_type="jira",
        source_instance=args.source_instance,
        mode=mode,
        run_id=effective_run_id,
    )

    logger.info("JIRA-Transform gestartet. mode=%s input=%s output=%s project=%s", mode, input_root, output_root, args.project or "*")

    for issue in loader.load_issues(project_filter=args.project):
        manifest.issues_seen += 1
        with audit.stage(
            run_id=run_context.run_id,
            source_type="jira",
            source_instance=args.source_instance,
            stage=AuditStage.DISCOVER,
            document_id=issue.issue_key,
            document_uri=issue.source_ref,
            document_title=issue.summary,
        ) as discover_evt:
            discover_evt.event.output_count = 1

        with audit.stage(
            run_id=run_context.run_id,
            source_type="jira",
            source_instance=args.source_instance,
            stage=AuditStage.LOAD,
            document_id=issue.issue_key,
            document_uri=issue.source_ref,
            document_title=issue.summary,
        ) as load_evt:
            load_evt.event.output_count = len(issue.description)

        attachment_signature = ",".join(sorted(issue.attachment_paths))
        source_checksum = stable_hash("|".join([issue.issue_key, issue.summary, issue.description, issue.updated_at or "", ",".join(issue.labels), attachment_signature]))
        old = state.issues.get(issue.issue_key)

        output_path = writer.build_output_path(issue.project_key, issue.issue_key, issue.summary)
        if not args.full_refresh and old and old.source_checksum == source_checksum and Path(old.output_file).exists():
            with audit.stage(
                run_id=run_context.run_id,
                source_type="jira",
                source_instance=args.source_instance,
                stage=AuditStage.FILTER,
                document_id=issue.issue_key,
                document_uri=issue.source_ref,
                document_title=issue.summary,
                extra_json={"changed_flag": False, "is_dirty": False},
            ) as filter_evt:
                filter_evt.skipped(ReasonCode.UNCHANGED_INCREMENTAL, "Issue unverändert")

            manifest.issues_skipped += 1
            manifest.records.append(
                JiraTransformRecord(
                    issue_key=issue.issue_key,
                    title=issue.summary,
                    source_ref=issue.source_ref,
                    output_file=old.output_file,
                    source_checksum=source_checksum,
                    output_checksum=old.output_checksum,
                    warning_count=0,
                    status="skipped",
                )
            )
            logger.debug("Issue übersprungen (unverändert): issue_key=%s", issue.issue_key)
            continue

        try:
            with audit.stage(
                run_id=run_context.run_id,
                source_type="jira",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=issue.issue_key,
                document_uri=issue.source_ref,
                document_title=issue.summary,
                extra_json={"changed_flag": True, "is_dirty": True},
            ) as transform_evt:
                transform_evt.event.input_count = len(issue.description)
                transformed = transformer.transform(issue)
                markdown = renderer.render(transformed)
                transform_evt.event.output_count = len(markdown)
                if not markdown.strip():
                    transform_evt.skipped(ReasonCode.EMPTY_AFTER_TRANSFORM, "Nach Rendering kein Text übrig")

            with audit.stage(
                run_id=run_context.run_id,
                source_type="jira",
                source_instance=args.source_instance,
                stage=AuditStage.CHUNK,
                document_id=issue.issue_key,
                document_uri=issue.source_ref,
                document_title=issue.summary,
            ) as chunk_evt:
                chunk_evt.event.input_count = len(markdown)
                chunk_evt.event.chunk_count = 1 if markdown.strip() else 0
                chunk_evt.event.output_count = chunk_evt.event.chunk_count
                if chunk_evt.event.chunk_count == 0:
                    chunk_evt.skipped(ReasonCode.NO_CHUNKS_CREATED, "Transformiertes Markdown ist leer")

            writer.write_markdown(output_path, markdown)

            output_checksum = stable_hash(markdown)
            state.issues[issue.issue_key] = JiraTransformStateRecord(
                source_checksum=source_checksum,
                output_checksum=output_checksum,
                output_file=str(output_path),
                updated_at=utc_now_iso(),
            )

            manifest.issues_processed += 1
            manifest.records.append(
                JiraTransformRecord(
                    issue_key=issue.issue_key,
                    title=issue.summary,
                    source_ref=issue.source_ref,
                    output_file=str(output_path),
                    source_checksum=source_checksum,
                    output_checksum=output_checksum,
                    warning_count=len(transformed.transform_warnings),
                    status="processed",
                )
            )
            logger.debug("Issue verarbeitet: issue_key=%s title=%s", issue.issue_key, issue.summary)
        except Exception as exc:  # noqa: BLE001
            with audit.stage(
                run_id=run_context.run_id,
                source_type="jira",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=issue.issue_key,
                document_uri=issue.source_ref,
                document_title=issue.summary,
            ) as error_evt:
                error_evt.error(ReasonCode.TRANSFORM_EXCEPTION, str(exc))

            manifest.issues_failed += 1
            manifest.records.append(
                JiraTransformRecord(
                    issue_key=issue.issue_key,
                    title=issue.summary,
                    source_ref=issue.source_ref,
                    output_file=str(output_path),
                    source_checksum=source_checksum,
                    output_checksum="",
                    warning_count=0,
                    status="error",
                )
            )
            logger.exception("Fehler bei Issue issue_key=%s: %s", issue.issue_key, exc)

    manifest.finished_at = utc_now_iso()
    manifest.run_duration = perf_counter() - started_perf
    manifest.run_duration_human = format_duration_human(manifest.run_duration)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    latest_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "JIRA-Transform beendet. run_id=%s seen=%s processed=%s skipped=%s failed=%s warnings=%s outputs=%s duration=%.2fs (%s)",
        manifest.run_id,
        manifest.issues_seen,
        manifest.issues_processed,
        manifest.issues_skipped,
        manifest.issues_failed,
        sum(record.warning_count for record in manifest.records),
        manifest.issues_processed,
        manifest.run_duration,
        manifest.run_duration_human,
    )
    logger.debug("Transform-Manifest: %s", run_manifest_path)
    logger.debug("Transform-State: %s", state_path)
    run_context.finish(status="finished" if manifest.issues_failed == 0 else "finished_with_errors")
    return 0 if manifest.issues_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
