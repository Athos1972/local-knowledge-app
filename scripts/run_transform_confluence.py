#!/usr/bin/env python3
"""CLI für die Transformation von Confluence-Exporten in Markdown."""

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
from processing.confluence.markdown_renderer import MarkdownRenderer
from processing.confluence.transform_manifest import (
    TransformRecord,
    TransformRunManifest,
    generate_transform_run_id,
)
from processing.confluence.transform_state import TransformState, TransformStateRecord
from processing.confluence.transformer import ConfluenceTransformer
from processing.confluence.writer import ConfluenceTransformWriter
from processing.frontmatter_schema import parse_frontmatter
from sources.confluence_export.confluence_export_loader import ConfluenceExportLoader
from sources.document import stable_hash, utc_now_iso


def parse_args() -> argparse.Namespace:
    """Liest CLI-Parameter für den Transform-Lauf."""
    parser = argparse.ArgumentParser(description="Confluence export transform")
    parser.add_argument("--full-refresh", "--full", dest="full_refresh", action="store_true")
    parser.add_argument("--space", dest="space", default=None, help="Optionaler Space-Key-Filter")
    parser.add_argument("--input-root", dest="input_root", default=None)
    parser.add_argument("--output-root", dest="output_root", default=None)
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--source-instance", dest="source_instance", default="confluence-export")
    return parser.parse_args()


def main() -> int:
    """Führt den Confluence-Transform-Lauf aus."""
    args = parse_args()

    data_root = Path.home() / "local-knowledge-data"
    default_input_root = data_root / "exports" / "confluence"
    default_output_root = data_root / "staging" / "confluence"

    input_root = Path(args.input_root).expanduser() if args.input_root else AppConfig.get_path(None, "confluence_transform", "input_root", default=str(default_input_root))
    output_root = Path(args.output_root).expanduser() if args.output_root else AppConfig.get_path(None, "confluence_transform", "output_root", default=str(default_output_root))
    manifests_dir = AppConfig.get_path(None, "confluence_transform", "manifests_dir", default=str(data_root / "system" / "confluence_transform"))

    minimum_chars_in_raw_page = int(AppConfig.get("confluence_transform", "minimum_number_of_raw_characters_in_page", default=0) or 0)
    minimum_chars_in_final_page = int(
        AppConfig.get("confluence_transform", "minimum_count_characters_confluence_final_page", default=200) or 200
    )

    mode = "full" if args.full_refresh else "incremental"
    effective_run_id = args.run_id or generate_transform_run_id()
    manifest = TransformRunManifest(run_id=effective_run_id, started_at=utc_now_iso(), mode=mode)
    logger = get_logger("run_transform_confluence", run_id=manifest.run_id)
    started_perf = perf_counter()

    loader = ConfluenceExportLoader(input_root)
    transformer = ConfluenceTransformer()
    renderer = MarkdownRenderer()
    writer = ConfluenceTransformWriter(output_root)

    state_path = manifests_dir / "latest_transform_state.json"
    latest_manifest_path = manifests_dir / "latest_transform_manifest.json"
    run_manifest_path = manifests_dir / f"run_{manifest.run_id}.json"

    state = TransformState.load(state_path)
    run_context, audit = build_audit_components(
        data_root=data_root,
        source_type="confluence",
        source_instance=args.source_instance,
        mode=mode,
        run_id=effective_run_id,
    )

    logger.info("Confluence-Transform gestartet. mode=%s input=%s output=%s space=%s", mode, input_root, output_root, args.space or "*")

    for page in loader.load_pages(space_filter=args.space):
        manifest.pages_seen += 1
        with audit.stage(
            run_id=run_context.run_id,
            source_type="confluence",
            source_instance=args.source_instance,
            stage=AuditStage.DISCOVER,
            document_id=page.page_id,
            document_uri=page.source_ref,
            document_title=page.title,
        ) as discover_evt:
            discover_evt.event.output_count = 1

        with audit.stage(
            run_id=run_context.run_id,
            source_type="confluence",
            source_instance=args.source_instance,
            stage=AuditStage.LOAD,
            document_id=page.page_id,
            document_uri=page.source_ref,
            document_title=page.title,
        ) as load_evt:
            load_evt.event.output_count = len(page.body)
        output_path = writer.build_output_path(page.space_key, page.page_id, page.title)

        if transformer.should_ignore_page(page):
            logger.debug("Seite wegen Titelregel übersprungen: page_id=%s title=%s", page.page_id, page.title)
            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.FILTER,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
                extra_json={"changed_flag": False, "is_dirty": False},
            ) as filter_evt:
                filter_evt.skipped(ReasonCode.FILTERED_BY_RULE, "Log-Seite per Titelregel ignoriert")

            manifest.pages_skipped += 1
            manifest.records.append(
                TransformRecord(
                    page_id=page.page_id,
                    title=page.title,
                    source_ref=page.source_ref,
                    output_file=str(output_path),
                    source_checksum="",
                    output_checksum="",
                    warning_count=0,
                    status="skipped",
                )
            )
            continue

        if minimum_chars_in_raw_page > 0 and len(page.body) < minimum_chars_in_raw_page:
            logger.debug(
                "Seite hatte %s Zeichen. Limit %s. Übersprungen.",
                len(page.body),
                minimum_chars_in_raw_page,
            )
            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.FILTER,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
                extra_json={"changed_flag": False, "is_dirty": False},
            ) as filter_evt:
                filter_evt.skipped(ReasonCode.TOO_SMALL_FOR_CHUNKING, "Seite unter Mindestzeichenanzahl")

            manifest.pages_skipped += 1
            manifest.records.append(
                TransformRecord(
                    page_id=page.page_id,
                    title=page.title,
                    source_ref=page.source_ref,
                    output_file=str(output_path),
                    source_checksum="",
                    output_checksum="",
                    warning_count=0,
                    status="skipped",
                )
            )
            continue

        source_checksum = stable_hash("|".join([page.title, page.body, page.updated_at or "", ",".join(page.labels)]))
        old = state.pages.get(page.page_id)

        if not args.full_refresh and old and old.source_checksum == source_checksum and Path(old.output_file).exists():
            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.FILTER,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
                extra_json={"changed_flag": False, "is_dirty": False},
            ) as filter_evt:
                filter_evt.skipped(ReasonCode.UNCHANGED_INCREMENTAL, "Seite unverändert")

            manifest.pages_skipped += 1
            manifest.records.append(
                TransformRecord(
                    page_id=page.page_id,
                    title=page.title,
                    source_ref=page.source_ref,
                    output_file=old.output_file,
                    source_checksum=source_checksum,
                    output_checksum=old.output_checksum,
                    warning_count=0,
                    status="skipped",
                )
            )
            logger.debug("Seite übersprungen (unverändert): page_id=%s title=%s", page.page_id, page.title)
            continue

        try:
            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
                extra_json={"changed_flag": True, "is_dirty": True},
            ) as transform_evt:
                transform_evt.event.input_count = len(page.body)
                transformed = transformer.transform(page)
                markdown = renderer.render(transformed)
                transform_evt.event.output_count = len(markdown)
                transform_evt.event.extra_json = {
                    **(transform_evt.event.extra_json or {}),
                    "warning_flags": sorted({warning.code for warning in transformed.transform_warnings}),
                    "unsupported_macros": transformed.unsupported_macros,
                    "output_file": str(output_path),
                }
                if not markdown.strip():
                    transform_evt.skipped(ReasonCode.EMPTY_AFTER_TRANSFORM, "Nach Rendering kein Text übrig")

            _frontmatter, markdown_body = parse_frontmatter(markdown)
            final_body_char_count = len(markdown_body.strip())
            has_complex_tables = any(document.doc_type == "confluence_table" for document in transformed.extra_documents)
            if (
                minimum_chars_in_final_page > 0
                and final_body_char_count < minimum_chars_in_final_page
                and not has_complex_tables
            ):
                logger.debug(
                    "Finale Seite übersprungen: Anzahl Zeichen %s kleiner %s via Parameter minimum_count_characters_confluence_final_page.",
                    final_body_char_count,
                    minimum_chars_in_final_page,
                )
                with audit.stage(
                    run_id=run_context.run_id,
                    source_type="confluence",
                    source_instance=args.source_instance,
                    stage=AuditStage.FILTER,
                    document_id=page.page_id,
                    document_uri=page.source_ref,
                    document_title=page.title,
                    extra_json={
                        "changed_flag": True,
                        "is_dirty": True,
                        "final_body_char_count": final_body_char_count,
                        "minimum_count_characters_confluence_final_page": minimum_chars_in_final_page,
                    },
                ) as filter_evt:
                    filter_evt.skipped(
                        ReasonCode.TOO_SMALL_FOR_CHUNKING,
                        "Finale Seite unter Mindestzeichenanzahl ohne komplexe Tabellen.",
                    )

                manifest.pages_skipped += 1
                manifest.records.append(
                    TransformRecord(
                        page_id=page.page_id,
                        title=page.title,
                        source_ref=page.source_ref,
                        output_file=str(output_path),
                        source_checksum=source_checksum,
                        output_checksum="",
                        warning_count=len(transformed.transform_warnings),
                        status="skipped",
                    )
                )
                continue

            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.CHUNK,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
            ) as chunk_evt:
                chunk_evt.event.input_count = len(markdown)
                chunk_evt.event.chunk_count = 1 if markdown.strip() else 0
                chunk_evt.event.output_count = chunk_evt.event.chunk_count
                if chunk_evt.event.chunk_count == 0:
                    chunk_evt.skipped(ReasonCode.NO_CHUNKS_CREATED, "Transformiertes Markdown ist leer")

            writer.write_transformed_page(output_path, markdown, transformed)

            output_checksum = stable_hash(markdown)
            state.pages[page.page_id] = TransformStateRecord(
                source_checksum=source_checksum,
                output_checksum=output_checksum,
                output_file=str(output_path),
                updated_at=utc_now_iso(),
            )

            manifest.pages_processed += 1
            manifest.records.append(
                TransformRecord(
                    page_id=page.page_id,
                    title=page.title,
                    source_ref=page.source_ref,
                    output_file=str(output_path),
                    source_checksum=source_checksum,
                    output_checksum=output_checksum,
                    warning_count=len(transformed.transform_warnings),
                    status="processed",
                )
            )
            if transformed.transform_warnings:
                warning_codes = [w.code for w in transformed.transform_warnings]
                logger.warning(
                    "Seite verarbeitet mit Warnungen: page_id=%s warnings=%s",
                    page.page_id,
                    warning_codes,
                )
                if "unsupported_macro" in warning_codes and transformed.unsupported_macros:
                    logger.warning(
                        "Seite mit unsupported_macro: page_id=%s macros=%s",
                        page.page_id,
                        sorted(set(transformed.unsupported_macros)),
                    )
            else:
                logger.debug("Seite verarbeitet: page_id=%s title=%s", page.page_id, page.title)
        except Exception as exc:  # noqa: BLE001
            with audit.stage(
                run_id=run_context.run_id,
                source_type="confluence",
                source_instance=args.source_instance,
                stage=AuditStage.TRANSFORM,
                document_id=page.page_id,
                document_uri=page.source_ref,
                document_title=page.title,
            ) as error_evt:
                error_evt.error(ReasonCode.TRANSFORM_EXCEPTION, str(exc))

            manifest.pages_failed += 1
            manifest.records.append(
                TransformRecord(
                    page_id=page.page_id,
                    title=page.title,
                    source_ref=page.source_ref,
                    output_file=str(output_path),
                    source_checksum=source_checksum,
                    output_checksum="",
                    warning_count=0,
                    status="error",
                )
            )
            logger.exception("Fehler bei Seite page_id=%s: %s", page.page_id, exc)


    logger.info("Finalisiere Terminologie-Kandidatenreport am Laufende.")
    try:
        report_path = transformer.finalize_terminology_report()
        if report_path is None:
            logger.info("Terminologie-Kandidatenreport: keine Kandidaten, nichts geschrieben.")
        else:
            exists_flag = report_path.exists()
            logger.info("Terminologie-Kandidatenreport finalisiert: path=%s exists=%s", report_path, exists_flag)
    except Exception as exc:  # noqa: BLE001
        # Report-Schreibfehler markieren den Run bewusst als fehlerhaft, da ein erwartetes Artefakt fehlt.
        manifest.pages_failed += 1
        logger.exception("Fehler beim Finalisieren des Terminologie-Kandidatenreports: %s", exc)

    manifest.finished_at = utc_now_iso()
    manifest.run_duration = perf_counter() - started_perf
    manifest.run_duration_human = format_duration_human(manifest.run_duration)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    latest_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "Confluence-Transform beendet. run_id=%s seen=%s processed=%s skipped=%s failed=%s warnings=%s outputs=%s duration=%.2fs (%s)",
        manifest.run_id,
        manifest.pages_seen,
        sum(1 for record in manifest.records if record.status == "processed"),
        manifest.pages_skipped,
        manifest.pages_failed,
        sum(record.warning_count for record in manifest.records),
        sum(1 for record in manifest.records if record.status == "processed"),
        manifest.run_duration,
        manifest.run_duration_human,
    )
    logger.debug("Transform-Manifest: %s", run_manifest_path)
    logger.debug("Transform-State: %s", state_path)
    run_context.finish(status="finished" if manifest.pages_failed == 0 else "finished_with_errors")
    return 0 if manifest.pages_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
