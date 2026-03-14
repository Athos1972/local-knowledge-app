#!/usr/bin/env python3
"""CLI for transforming local Office/PDF-style documents into Markdown."""

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
from processing.documents.domain_mapper import DomainMapper
from processing.documents.file_loader import DocumentFileLoader
from processing.documents.frontmatter import build_document_frontmatter
from processing.documents.manifest import (
    DocumentTransformRecord,
    DocumentTransformRunManifest,
    generate_transform_run_id,
)
from processing.documents.state import DocumentTransformState, DocumentTransformStateRecord
from processing.documents.writer import DocumentsTransformWriter
from sources.document import stable_hash, utc_now_iso
from transformers.markitdown_transformer import MarkItDownTransformer


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for documents transform runs."""
    parser = argparse.ArgumentParser(description="Transform local document exports into markdown")
    parser.add_argument("--full-refresh", "--full", dest="full_refresh", action="store_true")
    parser.add_argument("--input-root", dest="input_root", default=None)
    parser.add_argument("--output-root", dest="output_root", default=None)
    parser.add_argument("--publish-root", dest="publish_root", default=None)
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--source-instance", dest="source_instance", default="documents-local")
    return parser.parse_args()


def main() -> int:
    """Execute a documents transformation run."""
    args = parse_args()

    data_root = Path.home() / "local-knowledge-data"
    default_input_root = data_root / "exports" / "documents"
    default_output_root = data_root / "staging" / "documents"
    default_publish_root = data_root / "ingest" / "domains"
    default_manifests_dir = data_root / "system" / "documents_transform"

    input_root = Path(args.input_root).expanduser() if args.input_root else AppConfig.get_path(None, "documents_transform", "input_root", default=str(default_input_root))
    output_root = Path(args.output_root).expanduser() if args.output_root else AppConfig.get_path(None, "documents_transform", "output_root", default=str(default_output_root))
    publish_root = Path(args.publish_root).expanduser() if args.publish_root else AppConfig.get_path(None, "documents_transform", "publish_root", default=str(default_publish_root))
    manifests_dir = AppConfig.get_path(None, "documents_transform", "manifests_dir", default=str(default_manifests_dir))

    if not input_root.exists():
        print(f"ERROR: documents input root not found: {input_root}", file=sys.stderr)
        return 1

    fallback_domain = str(AppConfig.get("documents_transform", "fallback_domain", default="misc_documents"))
    mapping_data = AppConfig.get("documents_transform", "mapping", default=[])
    domain_mapper = DomainMapper.from_config(mapping_data, fallback_domain=fallback_domain)

    mode = "full" if args.full_refresh else "incremental"
    effective_run_id = args.run_id or generate_transform_run_id()
    manifest = DocumentTransformRunManifest(run_id=effective_run_id, started_at=utc_now_iso(), mode=mode)
    logger = get_logger("run_transform_documents", run_id=manifest.run_id)
    started_perf = perf_counter()

    transformer = MarkItDownTransformer()
    loader = DocumentFileLoader(input_root=input_root, transformer=transformer)
    writer = DocumentsTransformWriter(output_root=output_root, publish_root=publish_root)

    state_path = manifests_dir / "latest_transform_state.json"
    latest_manifest_path = manifests_dir / "latest_transform_manifest.json"
    run_manifest_path = manifests_dir / f"run_{manifest.run_id}.json"
    state = DocumentTransformState.load(state_path)

    logger.info(
        "Documents transform gestartet. mode=%s input=%s output=%s publish=%s source_instance=%s",
        mode,
        input_root,
        output_root,
        publish_root,
        args.source_instance,
    )

    for document in loader.load_documents():
        manifest.documents_seen += 1
        domain = domain_mapper.resolve_domain(document.relative_path)
        paths = writer.build_paths(
            relative_source_path=document.relative_path,
            domain=domain,
            document_id=document.document_id,
            title=document.source_path.stem,
        )

        stat = document.source_path.stat()
        source_checksum = stable_hash(f"{document.relative_path.as_posix()}|{stat.st_size}|{stat.st_mtime_ns}")
        old = state.documents.get(document.document_id)

        if (
            not args.full_refresh
            and old is not None
            and old.source_checksum == source_checksum
            and Path(old.staging_output_file).exists()
            and Path(old.publish_output_file).exists()
        ):
            manifest.documents_skipped += 1
            manifest.records.append(
                DocumentTransformRecord(
                    document_id=document.document_id,
                    source_path=document.source_path_value,
                    domain=domain,
                    staging_output_file=old.staging_output_file,
                    publish_output_file=old.publish_output_file,
                    source_checksum=source_checksum,
                    output_checksum="",
                    warning_count=0,
                    status="skipped",
                )
            )
            continue

        try:
            result = transformer.transform(document.source_path)
            if not result.success:
                raise RuntimeError(result.error or "Unknown transformer error")

            frontmatter = build_document_frontmatter(
                title=document.source_path.stem,
                source_system=document.source_system,
                source_collection=document.source_collection,
                source_path=document.source_path_value,
                domain=domain,
                document_id=document.document_id,
                metadata=result.metadata,
                transformer_name=transformer.name,
                transformer_version=transformer.version,
            )

            writer.write_document(paths=paths, frontmatter=frontmatter, markdown_body=result.markdown)
            output_checksum = stable_hash(result.markdown)

            state.documents[document.document_id] = DocumentTransformStateRecord(
                source_checksum=source_checksum,
                source_mtime=stat.st_mtime,
                source_size_bytes=stat.st_size,
                staging_output_file=str(paths.staging_path),
                publish_output_file=str(paths.publish_path),
                updated_at=utc_now_iso(),
            )

            manifest.documents_processed += 1
            manifest.records.append(
                DocumentTransformRecord(
                    document_id=document.document_id,
                    source_path=document.source_path_value,
                    domain=domain,
                    staging_output_file=str(paths.staging_path),
                    publish_output_file=str(paths.publish_path),
                    source_checksum=source_checksum,
                    output_checksum=output_checksum,
                    warning_count=len(result.warnings),
                    status="processed",
                )
            )
            if result.warnings:
                logger.warning("Dokument verarbeitet mit Warnungen: source=%s warnings=%s", document.source_path_value, result.warnings)
        except Exception as exc:  # noqa: BLE001
            manifest.documents_failed += 1
            manifest.records.append(
                DocumentTransformRecord(
                    document_id=document.document_id,
                    source_path=document.source_path_value,
                    domain=domain,
                    staging_output_file=str(paths.staging_path),
                    publish_output_file=str(paths.publish_path),
                    source_checksum=source_checksum,
                    output_checksum="",
                    warning_count=0,
                    status="error",
                )
            )
            logger.exception("Fehler bei Dokument source=%s: %s", document.source_path_value, exc)

    manifest.finished_at = utc_now_iso()
    manifest.run_duration = perf_counter() - started_perf
    manifest.run_duration_human = format_duration_human(manifest.run_duration)

    manifests_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    latest_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "Documents transform beendet. run_id=%s seen=%s processed=%s skipped=%s failed=%s duration=%.2fs (%s)",
        manifest.run_id,
        manifest.documents_seen,
        manifest.documents_processed,
        manifest.documents_skipped,
        manifest.documents_failed,
        manifest.run_duration,
        manifest.run_duration_human,
    )
    return 0 if manifest.documents_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
