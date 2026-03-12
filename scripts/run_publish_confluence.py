#!/usr/bin/env python3
"""CLI für das Publizieren von Confluence-Staging nach Domains."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_setup import get_logger
from common.time_utils import format_duration_human
from processing.publish.mapping_config import ConfluencePublishConfig
from processing.publish.publish_manifest import PublishRecord, PublishRunManifest, generate_publish_run_id
from processing.publish.publish_state import PublishState, PublishStateRecord
from processing.publish.publisher import ConfluencePublisher
from sources.document import stable_hash, utc_now_iso


def parse_args() -> argparse.Namespace:
    """Liest CLI-Parameter für den Publish-Lauf."""
    parser = argparse.ArgumentParser(description="Confluence staging publish")
    parser.add_argument("--full", "--full-refresh", dest="full_refresh", action="store_true")
    parser.add_argument("--space", dest="space", default=None, help="Optionaler Space-Key-Filter")
    parser.add_argument("--input-root", dest="input_root", default=None)
    parser.add_argument("--output-root", dest="output_root", default=None)
    parser.add_argument("--mapping-config", dest="mapping_config", default=None)
    return parser.parse_args()


def main() -> int:
    """Führt den Publish-Lauf robust und inkrementell aus."""
    args = parse_args()
    config = ConfluencePublishConfig.from_sources(
        input_root_override=args.input_root,
        output_root_override=args.output_root,
        mapping_config_path=args.mapping_config,
    )

    mode = "full" if args.full_refresh else "incremental"
    run_id = generate_publish_run_id()
    manifest = PublishRunManifest(run_id=run_id, started_at=utc_now_iso(), mode=mode)
    logger = get_logger("run_publish_confluence", run_id=run_id)
    started_perf = perf_counter()

    state_path = config.manifests_dir / "latest_publish_state.json"
    run_manifest_path = config.manifests_dir / f"run_{run_id}.json"
    latest_manifest_path = config.manifests_dir / "latest_publish_manifest.json"

    state = PublishState.load(state_path)
    publisher = ConfluencePublisher(config=config, logger=logger)

    files = publisher.discover_files(space_filter=args.space)
    logger.info(
        "Confluence-Publish gestartet. mode=%s input=%s output=%s files=%s space=%s",
        mode,
        config.input_root,
        config.output_root,
        len(files),
        args.space or "*",
    )

    for input_file in files:
        manifest.files_seen += 1
        state_key = str(input_file)
        state_record = state.files.get(state_key)
        source_checksum = stable_hash(input_file.read_text(encoding="utf-8"))

        if (
            not args.full_refresh
            and state_record
            and state_record.source_checksum == source_checksum
            and Path(state_record.output_file).exists()
        ):
            manifest.files_skipped += 1
            logger.debug("Datei übersprungen (unverändert): %s", input_file)
            manifest.records.append(
                PublishRecord(
                    input_file=str(input_file),
                    output_file=state_record.output_file,
                    page_id="",
                    title=input_file.stem,
                    space_key="",
                    source_checksum=source_checksum,
                    output_checksum=state_record.output_checksum,
                    status="skipped",
                    warning_count=0,
                )
            )
            continue

        try:
            result = publisher.publish_file(input_file)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fehler beim Publish: file=%s error=%s", input_file, exc)
            manifest.files_failed += 1
            manifest.records.append(
                PublishRecord(
                    input_file=str(input_file),
                    output_file="",
                    page_id="",
                    title=input_file.stem,
                    space_key="",
                    source_checksum=source_checksum,
                    output_checksum="",
                    status="error",
                    warning_count=1,
                )
            )
            continue

        if result.status == "error":
            manifest.files_failed += 1
            logger.warning("Datei mit Fehlerstatus verarbeitet: %s", input_file)
        else:
            if result.status == "unmapped":
                manifest.files_unmapped += 1
                logger.warning("Datei als unmapped publiziert: file=%s space=%s", input_file, result.space_key)
            else:
                logger.debug("Datei publiziert: file=%s output=%s", input_file, result.output_file)
            manifest.files_published += 1

        manifest.records.append(
            PublishRecord(
                input_file=str(result.input_file),
                output_file=str(result.output_file) if result.output_file else "",
                page_id=result.page_id,
                title=result.title,
                space_key=result.space_key,
                source_checksum=result.source_checksum,
                output_checksum=result.output_checksum,
                status=result.status,
                warning_count=result.warning_count,
            )
        )

        if result.output_file:
            state.files[state_key] = PublishStateRecord(
                source_checksum=result.source_checksum,
                output_checksum=result.output_checksum,
                output_file=str(result.output_file),
                updated_at=utc_now_iso(),
            )

    manifest.finished_at = utc_now_iso()
    manifest.run_duration = perf_counter() - started_perf
    manifest.run_duration_human = format_duration_human(manifest.run_duration)
    config.manifests_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    latest_manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    state.save(state_path)

    logger.info(
        "Confluence-Publish beendet. run_id=%s seen=%s published=%s skipped=%s failed=%s unmapped=%s duration=%.2fs (%s)",
        manifest.run_id,
        manifest.files_seen,
        manifest.files_published,
        manifest.files_skipped,
        manifest.files_failed,
        manifest.files_unmapped,
        manifest.run_duration,
        manifest.run_duration_human,
    )
    logger.debug("Publish-Manifest: %s", run_manifest_path)
    logger.debug("Publish-State: %s", state_path)
    return 0 if manifest.files_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
