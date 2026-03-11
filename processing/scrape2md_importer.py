from __future__ import annotations

import dataclasses
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tomllib
import yaml


LOGGER = logging.getLogger("scrape2md_importer")


@dataclass(slots=True)
class SourceConfig:
    export_root: Path
    source_key: str


@dataclass(slots=True)
class TargetConfig:
    knowledge_root: Path
    target_subpath: Path


@dataclass(slots=True)
class FrontmatterConfig:
    enabled: bool = True
    title_from_first_heading: bool = True


@dataclass(slots=True)
class BehaviorConfig:
    copy_assets: bool = False
    overwrite: bool = True
    dry_run: bool = False


@dataclass(slots=True)
class ImportConfig:
    source: SourceConfig
    target: TargetConfig
    frontmatter: FrontmatterConfig
    behavior: BehaviorConfig


@dataclass(slots=True)
class ImportStats:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)


def load_import_config(path: Path) -> ImportConfig:
    config_data = tomllib.loads(path.read_text(encoding="utf-8"))

    source = config_data.get("source", {})
    target = config_data.get("target", {})
    frontmatter = config_data.get("frontmatter", {})
    behavior = config_data.get("behavior", {})

    export_root = Path(str(source["export_root"])).expanduser()
    source_key = str(source.get("source_key") or export_root.name)
    knowledge_root = Path(str(target["knowledge_root"])).expanduser()
    target_subpath = Path(str(target["target_subpath"]))

    return ImportConfig(
        source=SourceConfig(export_root=export_root, source_key=source_key),
        target=TargetConfig(knowledge_root=knowledge_root, target_subpath=target_subpath),
        frontmatter=FrontmatterConfig(
            enabled=bool(frontmatter.get("enabled", True)),
            title_from_first_heading=bool(frontmatter.get("title_from_first_heading", True)),
        ),
        behavior=BehaviorConfig(
            copy_assets=bool(behavior.get("copy_assets", False)),
            overwrite=bool(behavior.get("overwrite", True)),
            dry_run=bool(behavior.get("dry_run", False)),
        ),
    )


def run_import(config: ImportConfig) -> ImportStats:
    stats = ImportStats()
    export_root = config.source.export_root
    pages_dir = export_root / "pages"

    if not export_root.exists():
        raise FileNotFoundError(f"Export root not found: {export_root}")
    if not pages_dir.exists():
        raise FileNotFoundError(f"pages directory not found: {pages_dir}")

    manifest = _load_manifest(export_root / "manifest.json")
    manifest_index = _build_manifest_index(manifest)

    destination_root = config.target.knowledge_root / config.target.target_subpath
    imported_at = _utc_timestamp()

    markdown_files = sorted(pages_dir.rglob("*.md"))
    LOGGER.info("Processing %s markdown files from %s", len(markdown_files), pages_dir)

    for source_file in markdown_files:
        relative_path = source_file.relative_to(pages_dir)
        target_file = destination_root / relative_path

        try:
            page_metadata = manifest_index.get(relative_path.as_posix(), {})
            result = _process_markdown_file(
                source_file=source_file,
                target_file=target_file,
                page_metadata=page_metadata,
                manifest=manifest,
                config=config,
                imported_at=imported_at,
            )
            if result == "imported":
                stats.imported += 1
            elif result == "updated":
                stats.updated += 1
            else:
                stats.skipped += 1
        except Exception as exc:  # pragma: no cover - defensive in batch processing
            message = f"{source_file}: {exc}"
            LOGGER.error("Failed to process %s", source_file, exc_info=exc)
            stats.errors.append(message)

    if config.behavior.copy_assets:
        _copy_assets_if_enabled(config, stats)

    return stats


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        LOGGER.warning("Manifest file missing: %s", manifest_path)
        return {}

    import json

    raw = manifest_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        return parsed
    LOGGER.warning("Manifest at %s is not a JSON object", manifest_path)
    return {}


def _build_manifest_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    candidates = manifest.get("pages") or manifest.get("documents") or manifest.get("items") or []
    if not isinstance(candidates, list):
        return index

    for item in candidates:
        if not isinstance(item, dict):
            continue
        rel_path = _extract_relative_markdown_path(item)
        if rel_path:
            index[rel_path] = item
    return index


def _extract_relative_markdown_path(item: dict[str, Any]) -> str | None:
    path_fields = (
        "markdown_rel_path",
        "relative_markdown_path",
        "markdown_path",
        "relative_path",
        "path",
        "file",
        "output_path",
    )

    for field in path_fields:
        value = item.get(field)
        if not value or not isinstance(value, str):
            continue

        normalized = value.replace("\\", "/")
        if "/pages/" in normalized:
            normalized = normalized.split("/pages/", 1)[1]
        elif normalized.startswith("pages/"):
            normalized = normalized[len("pages/") :]

        if normalized.endswith(".md"):
            return normalized

    return None


def _process_markdown_file(
    source_file: Path,
    target_file: Path,
    page_metadata: dict[str, Any],
    manifest: dict[str, Any],
    config: ImportConfig,
    imported_at: str,
) -> str:
    target_exists = target_file.exists()
    if target_exists and not config.behavior.overwrite:
        LOGGER.info("Skipping existing file (overwrite disabled): %s", target_file)
        return "skipped"

    original_text = source_file.read_text(encoding="utf-8")
    final_text = original_text

    if config.frontmatter.enabled:
        parsed_frontmatter, body = _parse_frontmatter(original_text)
        merged_frontmatter = _merge_frontmatter(
            existing=parsed_frontmatter,
            body=body,
            page_metadata=page_metadata,
            manifest=manifest,
            config=config,
            source_file=source_file,
            imported_at=imported_at,
        )
        final_text = _render_markdown_with_frontmatter(merged_frontmatter, body)

    if config.behavior.dry_run:
        LOGGER.info("[dry-run] Would write %s", target_file)
        return "updated" if target_exists else "imported"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(final_text, encoding="utf-8")
    LOGGER.info("Wrote %s", target_file)
    return "updated" if target_exists else "imported"


def _merge_frontmatter(
    existing: dict[str, Any],
    body: str,
    page_metadata: dict[str, Any],
    manifest: dict[str, Any],
    config: ImportConfig,
    source_file: Path,
    imported_at: str,
) -> dict[str, Any]:
    merged = dict(existing)

    source_domain = str(manifest.get("domain") or manifest.get("source_domain") or config.source.export_root.name)
    source_url = _pick_first_str(page_metadata, "source_url", "url", "canonical_url")
    crawl_timestamp = _pick_first_str(manifest, "crawl_timestamp", "exported_at", "created_at")
    title = _determine_title(existing, page_metadata, body, source_file, config)

    merged.update(
        {
            "title": title,
            "source_type": "external_website",
            "source_key": config.source.source_key,
            "source_domain": source_domain,
            "source_url": source_url or "",
            "original_url": source_url or "",
            "crawl_timestamp": crawl_timestamp or "",
            "imported_at": imported_at,
            "content_type": _pick_first_str(page_metadata, "content_type", "type") or "markdown",
            "status": str(existing.get("status") or "raw"),
        }
    )

    if "local_asset_refs" not in merged:
        merged["local_asset_refs"] = []
    if "tags" not in merged:
        merged["tags"] = []

    return merged


def _pick_first_str(values: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _determine_title(
    existing_frontmatter: dict[str, Any],
    page_metadata: dict[str, Any],
    body: str,
    source_file: Path,
    config: ImportConfig,
) -> str:
    existing_title = existing_frontmatter.get("title")
    if isinstance(existing_title, str) and existing_title.strip():
        return existing_title.strip()

    manifest_title = _pick_first_str(page_metadata, "title", "page_title")
    if manifest_title:
        return manifest_title

    if config.frontmatter.title_from_first_heading:
        heading = _extract_first_heading(body)
        if heading:
            return heading

    return source_file.stem.replace("-", " ").replace("_", " ").strip() or source_file.stem


def _extract_first_heading(markdown_body: str) -> str | None:
    heading_pattern = re.compile(r"^#\s+(.+?)\s*$", flags=re.MULTILINE)
    match = heading_pattern.search(markdown_body)
    if not match:
        return None
    return match.group(1).strip()


def _parse_frontmatter(markdown_text: str) -> tuple[dict[str, Any], str]:
    if not markdown_text.startswith("---\n"):
        return {}, markdown_text

    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown_text

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, markdown_text

    raw_frontmatter = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :])

    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, body


def _render_markdown_with_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    serialized = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    normalized_body = body.lstrip("\n")
    return f"---\n{serialized}\n---\n\n{normalized_body}\n"


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _copy_assets_if_enabled(config: ImportConfig, stats: ImportStats) -> None:
    source_assets = config.source.export_root / "assets"
    if not source_assets.exists():
        LOGGER.info("Assets copy enabled, but no assets folder found at %s", source_assets)
        return

    target_assets = config.target.knowledge_root / config.target.target_subpath / "assets"

    if config.behavior.dry_run:
        LOGGER.info("[dry-run] Would sync assets from %s to %s", source_assets, target_assets)
        return

    if target_assets.exists() and config.behavior.overwrite:
        shutil.rmtree(target_assets)

    if target_assets.exists() and not config.behavior.overwrite:
        LOGGER.info("Skipping asset copy (target exists and overwrite disabled): %s", target_assets)
        stats.skipped += 1
        return

    shutil.copytree(source_assets, target_assets)
    LOGGER.info("Copied assets directory to %s", target_assets)
