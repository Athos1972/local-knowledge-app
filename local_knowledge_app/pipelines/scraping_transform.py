from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from common.logging_setup import get_logger
from local_knowledge_app.transformers.router import TransformRouter

LOGGER = get_logger("scraping_transform")


@dataclass(slots=True)
class TransformRunConfig:
    input_root: Path
    output_root: Path
    dry_run: bool = False
    limit: int | None = None
    force: bool = False
    changed_only: bool = False


@dataclass(slots=True)
class TransformRunRecord:
    source_path: str
    relative_source_path: str
    markdown_path: str
    metadata_path: str
    transformer: str | None
    status: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class TransformRunReport:
    run_id: str
    started_at: str
    finished_at: str | None = None
    total_seen: int = 0
    total_supported: int = 0
    transformed: int = 0
    skipped: int = 0
    failed: int = 0
    records: list[TransformRunRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [asdict(record) for record in self.records]
        return payload


def run_transform(config: TransformRunConfig) -> TransformRunReport:
    run_id = f"scrape-transform-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    report = TransformRunReport(run_id=run_id, started_at=_now_iso())
    router = TransformRouter()

    if not config.input_root.exists():
        raise FileNotFoundError(f"input root not found: {config.input_root}")

    candidates = sorted(path for path in config.input_root.rglob("*") if path.is_file())
    report.total_seen = len(candidates)

    processed = 0
    for source_path in candidates:
        if config.limit is not None and processed >= config.limit:
            break

        transformer = router.resolve(source_path)
        if transformer is None:
            continue
        report.total_supported += 1

        rel_path = source_path.relative_to(config.input_root)
        markdown_target, metadata_target = _target_paths(config.output_root, rel_path)

        if config.changed_only and not config.force and _is_up_to_date(source_path, markdown_target, metadata_target):
            report.skipped += 1
            report.records.append(
                TransformRunRecord(
                    source_path=str(source_path),
                    relative_source_path=rel_path.as_posix(),
                    markdown_path=str(markdown_target),
                    metadata_path=str(metadata_target),
                    transformer=getattr(transformer, "name", None),
                    status="skipped",
                    warnings=["changed-only: existing artifacts are newer than source"],
                )
            )
            processed += 1
            continue

        result = transformer.transform(source_path)
        warnings = list(result.warnings)
        markdown = result.markdown
        if not markdown.strip():
            warnings.append("Empty markdown output")
        elif len(markdown.strip()) < 80:
            warnings.append("Markdown output is unusually short")

        payload = _build_metadata_payload(
            run_id=run_id,
            source_path=source_path,
            input_root=config.input_root,
            transformer_name=getattr(transformer, "name", "unknown"),
            transformer_version=getattr(transformer, "version", None),
            markdown=markdown,
            base_metadata=result.metadata,
            warnings=warnings,
            success=result.success,
            error=result.error,
        )

        if config.dry_run:
            LOGGER.info("[dry-run] Would write %s and %s", markdown_target, metadata_target)
            status = "failed" if not result.success else "dry-run"
            if status == "failed":
                report.failed += 1
            else:
                report.transformed += 1
            report.records.append(
                TransformRunRecord(
                    source_path=str(source_path),
                    relative_source_path=rel_path.as_posix(),
                    markdown_path=str(markdown_target),
                    metadata_path=str(metadata_target),
                    transformer=getattr(transformer, "name", None),
                    status=status,
                    warnings=warnings,
                    error=result.error,
                )
            )
            processed += 1
            continue

        markdown_target.parent.mkdir(parents=True, exist_ok=True)
        metadata_target.parent.mkdir(parents=True, exist_ok=True)

        if result.success:
            markdown_target.write_text(markdown, encoding="utf-8")
        else:
            markdown_target.write_text("", encoding="utf-8")
        metadata_target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        status = "failed" if not result.success else "transformed"
        if status == "failed":
            report.failed += 1
            LOGGER.error("Failed to transform %s: %s", source_path, result.error)
        else:
            report.transformed += 1
            LOGGER.info("Transformed %s -> %s", source_path, markdown_target)

        report.records.append(
            TransformRunRecord(
                source_path=str(source_path),
                relative_source_path=rel_path.as_posix(),
                markdown_path=str(markdown_target),
                metadata_path=str(metadata_target),
                transformer=getattr(transformer, "name", None),
                status=status,
                warnings=warnings,
                error=result.error,
            )
        )
        processed += 1

    report.finished_at = _now_iso()
    if not config.dry_run:
        _write_report(config.output_root, report)
    return report


def _target_paths(output_root: Path, relative_source_path: Path) -> tuple[Path, Path]:
    transformed_root = output_root / "scraping"
    base = transformed_root / relative_source_path
    suffix = relative_source_path.suffix
    stem = relative_source_path.name[: -len(suffix)] if suffix else relative_source_path.name
    markdown_target = base.with_name(f"{stem}.md")
    metadata_target = base.with_name(f"{stem}.meta.json")
    return markdown_target, metadata_target


def _is_up_to_date(source: Path, markdown_target: Path, metadata_target: Path) -> bool:
    if not markdown_target.exists() or not metadata_target.exists():
        return False
    source_mtime = source.stat().st_mtime
    return markdown_target.stat().st_mtime >= source_mtime and metadata_target.stat().st_mtime >= source_mtime


def _build_metadata_payload(
    *,
    run_id: str,
    source_path: Path,
    input_root: Path,
    transformer_name: str,
    transformer_version: str | None,
    markdown: str,
    base_metadata: dict[str, Any],
    warnings: list[str],
    success: bool,
    error: str | None,
) -> dict[str, Any]:
    rel_path = source_path.relative_to(input_root).as_posix()
    payload: dict[str, Any] = dict(base_metadata)
    payload.update(
        {
            "source_system": "scraping",
            "source_path": str(source_path),
            "relative_source_path": rel_path,
            "file_name": source_path.name,
            "extension": source_path.suffix.lower(),
            "transformer": transformer_name,
            "transformer_version": transformer_version,
            "transformed_at": _now_iso(),
            "warnings": warnings,
            "markdown_char_count": len(markdown),
            "markdown_line_count": len(markdown.splitlines()),
            "success": success,
            "run_id": run_id,
            "sha256": _sha256(source_path),
            "error": error,
        }
    )
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_report(output_root: Path, report: TransformRunReport) -> None:
    manifest_dir = output_root / "scraping"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"manifest_{report.run_id}.json"
    latest_path = manifest_dir / "manifest.latest.json"
    content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    manifest_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
