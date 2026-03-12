from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

import tomllib

from common.logging_setup import get_logger

LOGGER = get_logger("domain_mapping")


@dataclass(slots=True)
class MappingRule:
    id: str
    target_subpath: str
    path_prefix: str | None = None
    path_contains: str | None = None
    file_name_contains: str | None = None


@dataclass(slots=True)
class MappingConfig:
    default_target_subpath: str = "external/unassigned"
    rules: list[MappingRule] = field(default_factory=list)


@dataclass(slots=True)
class MapRunConfig:
    transformed_root: Path
    domains_root: Path
    mapping_config_path: Path
    dry_run: bool = False
    force: bool = False


@dataclass(slots=True)
class MapRunStats:
    seen: int = 0
    mapped: int = 0
    skipped: int = 0
    failed: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)


def load_mapping_config(path: Path) -> MappingConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    mapping = raw.get("mapping", {})
    default_target_subpath = str(mapping.get("default_target_subpath", "external/unassigned"))

    rules: list[MappingRule] = []
    for item in mapping.get("rules", []):
        if not isinstance(item, dict):
            continue
        rules.append(
            MappingRule(
                id=str(item.get("id", f"rule-{len(rules)+1}")),
                target_subpath=str(item["target_subpath"]),
                path_prefix=_optional_string(item.get("path_prefix")),
                path_contains=_optional_string(item.get("path_contains")),
                file_name_contains=_optional_string(item.get("file_name_contains")),
            )
        )

    return MappingConfig(default_target_subpath=default_target_subpath, rules=rules)


def run_mapping(config: MapRunConfig) -> MapRunStats:
    mapping_config = load_mapping_config(config.mapping_config_path)
    stats = MapRunStats()

    root = config.transformed_root / "scraping"
    metadata_files = sorted(root.rglob("*.meta.json"))

    for meta_path in metadata_files:
        stats.seen += 1
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            transformed_md_path = _resolve_markdown_path(meta_path)
            relative_source_path = str(metadata.get("relative_source_path", ""))
            rule = choose_mapping_rule(
                mapping_config,
                relative_source_path=relative_source_path,
                file_name=Path(relative_source_path).name,
            )

            if not transformed_md_path.exists():
                stats.failed += 1
                stats.records.append({"status": "failed", "meta_path": str(meta_path), "error": "markdown file missing"})
                continue

            destination_relative = Path(rule.target_subpath) / Path(relative_source_path).with_suffix(".md")
            destination_md = config.domains_root / destination_relative
            destination_meta = destination_md.with_suffix(".meta.json")

            if destination_md.exists() and not config.force:
                stats.skipped += 1
                stats.records.append({"status": "skipped", "target": str(destination_md), "rule": rule.id})
                continue

            merged_metadata = _build_domain_metadata(
                transformed_metadata=metadata,
                domain_path=rule.target_subpath,
                mapping_rule_id=rule.id,
                transformed_relative_path=transformed_md_path.relative_to(config.transformed_root).as_posix(),
            )

            if config.dry_run:
                stats.mapped += 1
                stats.records.append({"status": "dry-run", "target": str(destination_md), "rule": rule.id})
                continue

            destination_md.parent.mkdir(parents=True, exist_ok=True)
            destination_md.write_text(transformed_md_path.read_text(encoding="utf-8"), encoding="utf-8")
            destination_meta.write_text(json.dumps(merged_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            stats.mapped += 1
            stats.records.append({"status": "mapped", "target": str(destination_md), "rule": rule.id})
        except Exception as exc:
            LOGGER.error("Failed to map %s", meta_path, exc_info=exc)
            stats.failed += 1
            stats.records.append({"status": "failed", "meta_path": str(meta_path), "error": str(exc)})

    LOGGER.info(
        "Scraping-Mapping beendet. seen=%s mapped=%s skipped=%s failed=%s",
        stats.seen,
        stats.mapped,
        stats.skipped,
        stats.failed,
    )

    return stats


def choose_mapping_rule(mapping_config: MappingConfig, *, relative_source_path: str, file_name: str) -> MappingRule:
    normalized_path = relative_source_path.replace("\\", "/")
    normalized_file_name = file_name.lower()

    for rule in mapping_config.rules:
        if rule.path_prefix and not normalized_path.startswith(rule.path_prefix):
            continue
        if rule.path_contains and rule.path_contains not in normalized_path:
            continue
        if rule.file_name_contains and rule.file_name_contains.lower() not in normalized_file_name:
            continue
        return rule

    return MappingRule(id="default", target_subpath=mapping_config.default_target_subpath)


def derive_title_from_filename(path_or_name: str) -> str:
    name = Path(path_or_name).stem
    normalized = re.sub(r"[_\-]+", " ", name).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or "untitled"


def _resolve_markdown_path(meta_path: Path) -> Path:
    if meta_path.name.endswith(".meta.json"):
        return meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".md")
    return meta_path.with_suffix(".md")


def _build_domain_metadata(
    *,
    transformed_metadata: dict[str, Any],
    domain_path: str,
    mapping_rule_id: str,
    transformed_relative_path: str,
) -> dict[str, Any]:
    enriched = dict(transformed_metadata)
    enriched.update(
        {
            "domain": domain_path,
            "source_kind": "scraped_asset",
            "source_system": "scraping",
            "original_relative_path": transformed_metadata.get("relative_source_path"),
            "transformed_relative_path": transformed_relative_path,
            "mapping_rule_id": mapping_rule_id,
            "title": transformed_metadata.get("title") or derive_title_from_filename(str(transformed_metadata.get("file_name", ""))),
            "tags": transformed_metadata.get("tags") or [],
            "mapped_at": datetime.now(UTC).isoformat(),
        }
    )
    return enriched


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
