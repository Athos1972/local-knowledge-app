#!/usr/bin/env python3
"""CLI for transforming local Office/PDF-style documents into Markdown."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.config import AppConfig
from common.logging_setup import get_logger
from common.time_utils import format_duration_human
from processing.documents.domain_mapper import DomainMapper
from processing.documents.file_loader import DocumentFileLoader, DocumentSource
from processing.documents.frontmatter import build_document_frontmatter
from processing.documents.reference_resolver import resolve_document_reference
from processing.documents.manifest import (
    DocumentTransformRecord,
    DocumentTransformRunManifest,
    generate_transform_run_id,
)
from processing.documents.state import DocumentTransformState, DocumentTransformStateRecord
from processing.documents.writer import DocumentsTransformWriter
from sources.document import stable_hash, utc_now_iso
from transformers.markitdown_transformer import MarkItDownTransformer

SOURCE_PRIORITY: dict[str, int] = {
    "documents": 0,
    "jira": 1,
    "confluence": 2,
    "scraping": 3,
    "inbox": 4,
}


def build_source_roots(
    *,
    primary_input_root: Path,
    jira_root: Path,
    confluence_root: Path,
    scraping_root: Path,
    inbox_root: Path,
) -> list[DocumentSource]:
    """Build the default discovery roots for document-like files."""
    return [
        DocumentSource(origin="documents", root_path=primary_input_root),
        DocumentSource(origin="jira", root_path=jira_root),
        DocumentSource(origin="confluence", root_path=confluence_root),
        DocumentSource(origin="scraping", root_path=scraping_root),
        DocumentSource(origin="inbox", root_path=inbox_root),
    ]


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


def compute_file_sha256(path: Path) -> str:
    """Compute a stable SHA-256 checksum over the raw source bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dedupe_documents_by_content(documents: list[object]) -> tuple[list[object], list[tuple[object, object, str]]]:
    """Deduplicate discovered documents by file content and source priority."""
    selected_by_hash: dict[str, object] = {}
    duplicates: list[tuple[object, object, str]] = []

    def sort_key(document: object) -> tuple[int, str, str]:
        origin = str(getattr(document, "source_origin", "inbox"))
        return (
            SOURCE_PRIORITY.get(origin, 99),
            str(getattr(document, "routing_path", "")),
            str(getattr(document, "source_path", "")),
        )

    for document in sorted(documents, key=sort_key):
        checksum = compute_file_sha256(getattr(document, "source_path"))
        existing = selected_by_hash.get(checksum)
        if existing is None:
            selected_by_hash[checksum] = document
            continue
        duplicates.append((document, existing, checksum))

    selected = sorted(selected_by_hash.values(), key=sort_key)
    return selected, duplicates


def build_duplicate_aliases(duplicates: list[tuple[object, object, str]]) -> dict[str, list[str]]:
    """Collect skipped duplicate document ids as aliases for the kept document."""
    aliases_by_kept_id: dict[str, set[str]] = {}
    for skipped_document, kept_document, _checksum in duplicates:
        aliases_by_kept_id.setdefault(kept_document.document_id, set()).add(skipped_document.document_id)
    return {document_id: sorted(values) for document_id, values in aliases_by_kept_id.items()}


def build_parent_metadata(document: object, duplicate_documents: list[tuple[object, object, str]]) -> dict[str, object]:
    """Merge direct and deduplicated parent references for one kept document."""
    parent_refs: list[dict[str, object]] = []
    direct_reference = resolve_document_reference(getattr(document, "source_path"))
    if direct_reference and direct_reference.parent_metadata:
        parent_refs.append(dict(direct_reference.parent_metadata))

    for skipped_document, kept_document, _checksum in duplicate_documents:
        if kept_document.document_id != getattr(document, "document_id"):
            continue
        skipped_reference = resolve_document_reference(getattr(skipped_document, "source_path"))
        if skipped_reference and skipped_reference.parent_metadata:
            parent_refs.append(dict(skipped_reference.parent_metadata))

    if not parent_refs:
        return {}

    unique_parent_refs: list[dict[str, object]] = []
    seen = set()
    for item in parent_refs:
        signature = tuple(sorted((str(key), str(value)) for key, value in item.items()))
        if signature in seen:
            continue
        seen.add(signature)
        unique_parent_refs.append(item)

    primary = dict(unique_parent_refs[0])
    if len(unique_parent_refs) > 1:
        primary["parent_refs"] = unique_parent_refs
    return primary


def main() -> int:
    """Execute a documents transformation run."""
    args = parse_args()

    data_root = Path.home() / "local-knowledge-data"
    default_input_root = data_root / "exports" / "documents"
    default_jira_root = data_root / "exports" / "jira"
    default_confluence_root = data_root / "exports" / "confluence"
    default_scraping_root = data_root / "exports" / "scraping"
    default_inbox_root = data_root / "inbox"
    default_output_root = data_root / "staging" / "documents"
    default_publish_root = data_root / "ingest" / "domains"
    default_manifests_dir = data_root / "system" / "documents_transform"

    input_root = Path(args.input_root).expanduser() if args.input_root else AppConfig.get_path(None, "documents_transform", "input_root", default=str(default_input_root))
    output_root = Path(args.output_root).expanduser() if args.output_root else AppConfig.get_path(None, "documents_transform", "output_root", default=str(default_output_root))
    publish_root = Path(args.publish_root).expanduser() if args.publish_root else AppConfig.get_path(None, "documents_transform", "publish_root", default=str(default_publish_root))
    manifests_dir = AppConfig.get_path(None, "documents_transform", "manifests_dir", default=str(default_manifests_dir))

    source_roots = build_source_roots(
        primary_input_root=input_root,
        jira_root=AppConfig.get_path(None, "documents_transform", "jira_input_root", default=str(default_jira_root)),
        confluence_root=AppConfig.get_path(None, "documents_transform", "confluence_input_root", default=str(default_confluence_root)),
        scraping_root=AppConfig.get_path(None, "documents_transform", "scraping_input_root", default=str(default_scraping_root)),
        inbox_root=AppConfig.get_path(None, "documents_transform", "inbox_input_root", default=str(default_inbox_root)),
    )

    existing_source_roots = [source for source in source_roots if source.root_path.exists()]
    if not existing_source_roots:
        logger = get_logger("run_transform_documents", run_id=args.run_id or "documents-noop")
        logger.info("Keine Documents-Quellen gefunden. Erwartete Roots: %s", [str(source.root_path) for source in source_roots])
        return 0

    fallback_domain = str(AppConfig.get("documents_transform", "fallback_domain", default="misc_documents"))
    mapping_data = AppConfig.get("documents_transform", "mapping", default=[])
    domain_mapper = DomainMapper.from_config(mapping_data, fallback_domain=fallback_domain)

    mode = "full" if args.full_refresh else "incremental"
    effective_run_id = args.run_id or generate_transform_run_id()
    manifest = DocumentTransformRunManifest(run_id=effective_run_id, started_at=utc_now_iso(), mode=mode)
    logger = get_logger("run_transform_documents", run_id=manifest.run_id)
    started_perf = perf_counter()

    transformer = MarkItDownTransformer()
    loader = DocumentFileLoader(transformer=transformer, sources=source_roots)
    writer = DocumentsTransformWriter(output_root=output_root, publish_root=publish_root)

    state_path = manifests_dir / "latest_transform_state.json"
    latest_manifest_path = manifests_dir / "latest_transform_manifest.json"
    run_manifest_path = manifests_dir / f"run_{manifest.run_id}.json"
    state = DocumentTransformState.load(state_path)

    logger.info(
        "Documents transform gestartet. mode=%s input=%s output=%s publish=%s source_instance=%s",
        mode,
        [str(source.root_path) for source in existing_source_roots],
        output_root,
        publish_root,
        args.source_instance,
    )

    discovered_documents = list(loader.load_documents())
    manifest.documents_seen = len(discovered_documents)
    documents_to_process, duplicate_documents = dedupe_documents_by_content(discovered_documents)
    duplicate_aliases = build_duplicate_aliases(duplicate_documents)

    if duplicate_documents:
        logger.info(
            "Documents dedupe summary. discovered=%s unique=%s duplicates=%s",
            len(discovered_documents),
            len(documents_to_process),
            len(duplicate_documents),
        )
        for skipped_document, kept_document, checksum in duplicate_documents:
            manifest.documents_skipped += 1
            manifest.records.append(
                DocumentTransformRecord(
                    document_id=skipped_document.document_id,
                    source_path=skipped_document.source_path_value,
                    domain=domain_mapper.resolve_domain(skipped_document.routing_path),
                    staging_output_file="",
                    publish_output_file="",
                    source_checksum=checksum,
                    output_checksum="",
                    warning_count=0,
                    status=f"skipped_duplicate_of:{kept_document.document_id}",
                )
            )
            logger.debug(
                "Documents duplicate skipped. skipped=%s kept=%s checksum=%s",
                skipped_document.routing_path,
                kept_document.routing_path,
                checksum,
            )

    for document in documents_to_process:
        domain = domain_mapper.resolve_domain(document.routing_path)
        paths = writer.build_paths(
            relative_source_path=document.routing_path,
            domain=domain,
            document_id=document.document_id,
            title=document.source_path.stem,
        )

        stat = document.source_path.stat()
        source_checksum = stable_hash(f"{document.routing_path.as_posix()}|{stat.st_size}|{stat.st_mtime_ns}")
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
                source_origin=document.source_origin,
                source_system=document.source_system,
                source_collection=document.source_collection,
                source_path=document.source_path_value,
                logical_path=document.routing_path.as_posix(),
                domain=domain,
                document_id=document.document_id,
                aliases=duplicate_aliases.get(document.document_id, []),
                parent_metadata=build_parent_metadata(document, duplicate_documents),
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
