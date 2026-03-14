#!/usr/bin/env python3
"""Reset local pipeline state to a fresh-initialized baseline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.config import AppConfig
from common.logging_setup import get_logger

ALL_SCOPES = ("audit", "anythingllm", "staging", "derived", "reports", "logs", "index")


@dataclass(frozen=True, slots=True)
class DeletionTarget:
    category: str
    path: Path
    size_bytes: int
    reason: str


@dataclass(frozen=True, slots=True)
class ResetPaths:
    repo_root: Path
    data_root: Path
    confluence_staging_root: Path
    scraping_staging_root: Path
    jira_staging_root: Path
    confluence_transform_manifest_root: Path
    jira_transform_manifest_root: Path
    ingestion_manifest_root: Path
    confluence_publish_manifest_root: Path
    domains_root: Path
    reports_root: Path
    logs_root: Path
    scripts_logs_root: Path
    scipts_logs_root: Path
    index_root: Path
    processed_root: Path
    audit_root: Path
    anythingllm_root: Path


@dataclass(frozen=True, slots=True)
class ResetOptions:
    execute: bool
    yes: bool
    keep_exports: bool
    keep_anythingllm: bool
    scopes: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset local pipeline state (dry-run default)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan only (default)")
    mode.add_argument("--execute", action="store_true", help="Actually delete selected artifacts")

    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation for --execute")
    parser.add_argument("--keep-exports", action="store_true", help="Compatibility flag (exports are always kept)")
    parser.add_argument("--keep-anythingllm", action="store_true", help="Do not delete local AnythingLLM ingest state")
    parser.add_argument(
        "--scope",
        default=",".join(ALL_SCOPES),
        help=f"Comma-separated scopes from: {', '.join(ALL_SCOPES)}",
    )
    return parser.parse_args()


def _resolve_path(raw: Path, *, repo_root: Path) -> Path:
    expanded = raw.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (repo_root / expanded).resolve()


def load_reset_paths(repo_root: Path) -> ResetPaths:
    data_root = AppConfig.get_path("DATA_ROOT", "paths", "data_root", default=str(Path.home() / "local-knowledge-data")).resolve()
    confluence_staging = _resolve_path(
        AppConfig.get_path(None, "confluence_transform", "output_root", default=str(data_root / "staging" / "confluence")),
        repo_root=repo_root,
    )
    scraping_staging = _resolve_path(
        AppConfig.get_path(None, "scraping_transform", "output_root", default="staging/transformed"),
        repo_root=repo_root,
    )
    jira_staging = _resolve_path(
        AppConfig.get_path(None, "jira_transform", "output_root", default=str(data_root / "staging" / "jira")),
        repo_root=repo_root,
    )
    confluence_transform_manifest = _resolve_path(
        AppConfig.get_path(None, "confluence_transform", "manifests_dir", default=str(data_root / "system" / "confluence_transform")),
        repo_root=repo_root,
    )
    jira_transform_manifest = _resolve_path(
        AppConfig.get_path(None, "jira_transform", "manifests_dir", default=str(data_root / "system" / "jira_transform")),
        repo_root=repo_root,
    )
    ingestion_manifest_root = (data_root / "system" / "manifests").resolve()
    confluence_publish_manifest = _resolve_path(
        AppConfig.get_path(None, "publish", "confluence", "manifests_dir", default=str(data_root / "system" / "confluence_publish")),
        repo_root=repo_root,
    )
    domains_root = _resolve_path(
        AppConfig.get_path(None, "publish", "confluence", "output_root", default=str(data_root / "domains")),
        repo_root=repo_root,
    )
    reports_root = (repo_root / "reports").resolve()
    logs_root = _resolve_path(AppConfig.get_path(None, "logging", "log_dir", default="logs"), repo_root=repo_root)
    scripts_logs_root = (repo_root / "scripts" / "logs").resolve()
    scipts_logs_root = (repo_root / "scipts" / "logs").resolve()

    return ResetPaths(
        repo_root=repo_root,
        data_root=data_root,
        confluence_staging_root=confluence_staging,
        scraping_staging_root=scraping_staging,
        jira_staging_root=jira_staging,
        confluence_transform_manifest_root=confluence_transform_manifest,
        jira_transform_manifest_root=jira_transform_manifest,
        ingestion_manifest_root=ingestion_manifest_root,
        confluence_publish_manifest_root=confluence_publish_manifest,
        domains_root=domains_root,
        reports_root=reports_root,
        logs_root=logs_root,
        scripts_logs_root=scripts_logs_root,
        scipts_logs_root=scipts_logs_root,
        index_root=(data_root / "index").resolve(),
        processed_root=(data_root / "processed").resolve(),
        audit_root=(data_root / "system" / "audit").resolve(),
        anythingllm_root=(data_root / "system" / "anythingllm_ingest").resolve(),
    )


def parse_options(args: argparse.Namespace) -> ResetOptions:
    scopes = tuple(scope.strip().lower() for scope in args.scope.split(",") if scope.strip())
    invalid = [scope for scope in scopes if scope not in ALL_SCOPES]
    if invalid:
        raise ValueError(f"Unknown scope(s): {', '.join(invalid)}")

    execute = bool(args.execute)
    if not args.execute and not args.dry_run:
        execute = False

    return ResetOptions(
        execute=execute,
        yes=bool(args.yes),
        keep_exports=bool(args.keep_exports),
        keep_anythingllm=bool(args.keep_anythingllm),
        scopes=scopes,
    )


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (path for path in root.rglob("*") if path.is_file())


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _add_targets(targets: list[DeletionTarget], category: str, paths: Iterable[Path], reason: str) -> None:
    for path in paths:
        if path.exists() and path.is_file():
            targets.append(DeletionTarget(category=category, path=path.resolve(), size_bytes=_file_size(path), reason=reason))


def _discover_derived_domain_targets(domains_root: Path) -> list[Path]:
    if not domains_root.exists():
        return []

    candidates: list[Path] = []
    for meta_file in domains_root.rglob("*.meta.json"):
        try:
            payload = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        source_system = str(payload.get("source_system", "")).strip().lower()
        transformed = payload.get("transformed_relative_path")
        if source_system not in {"scraping", "confluence"} and not transformed:
            continue

        candidates.append(meta_file)
        sibling_md = meta_file.with_name(meta_file.name[: -len(".meta.json")] + ".md")
        if sibling_md.exists():
            candidates.append(sibling_md)

    return candidates


def collect_targets(paths: ResetPaths, options: ResetOptions) -> tuple[list[DeletionTarget], list[str]]:
    targets: list[DeletionTarget] = []
    kept: list[str] = ["exports/* (raw data is always preserved)"]
    if options.keep_exports:
        kept.append("--keep-exports gesetzt (Hinweis: exports werden ohnehin nie gelöscht)")

    selected = set(options.scopes)

    if "audit" in selected:
        _add_targets(targets, "audit", [paths.audit_root / "pipeline_audit.sqlite"], "Audit SQLite DB")
        _add_targets(targets, "audit", _iter_files(paths.audit_root / "runs"), "Audit JSONL runs")

    if "anythingllm" in selected:
        if options.keep_anythingllm:
            kept.append("anythingllm scope durch --keep-anythingllm bewusst behalten")
        else:
            names = {"latest_state.json", "latest_manifest.json"}
            files = [p for p in _iter_files(paths.anythingllm_root) if p.name in names or p.name.startswith("run_")]
            _add_targets(targets, "anythingllm", files, "AnythingLLM local delta/manifests")

    if "staging" in selected:
        _add_targets(targets, "staging", _iter_files(paths.confluence_staging_root), "Confluence staging output")
        _add_targets(targets, "staging", _iter_files(paths.scraping_staging_root), "Scraping transformed output")
        _add_targets(targets, "staging", _iter_files(paths.jira_staging_root), "Jira staging output")
        _add_targets(targets, "staging", _iter_files(paths.processed_root), "Ingestion processed artifacts")
        _add_targets(targets, "staging", _iter_files(paths.confluence_transform_manifest_root), "Confluence transform state")
        _add_targets(targets, "staging", _iter_files(paths.jira_transform_manifest_root), "Jira transform state")
        _add_targets(targets, "staging", _iter_files(paths.ingestion_manifest_root), "Ingestion run manifests/state")

    if "derived" in selected:
        _add_targets(
            targets,
            "derived",
            _discover_derived_domain_targets(paths.domains_root),
            "Derived domain markdown + metadata (detected via *.meta.json)",
        )
        _add_targets(targets, "derived", _iter_files(paths.confluence_publish_manifest_root), "Confluence publish state")

    if "reports" in selected:
        report_files = [p for p in _iter_files(paths.reports_root) if p.suffix.lower() in {".md", ".json", ".csv"}]
        _add_targets(targets, "reports", report_files, "Generated reports")

    if "logs" in selected:
        _add_targets(targets, "logs", _iter_files(paths.logs_root), "Repo log files")
        _add_targets(targets, "logs", _iter_files(paths.scripts_logs_root), "Script log files")
        _add_targets(targets, "logs", _iter_files(paths.scipts_logs_root), "Legacy/typo scipts log files")

    if "index" in selected:
        _add_targets(targets, "index", _iter_files(paths.index_root), "Vector index artifacts")

    unique = {(target.category, target.path): target for target in targets}
    return sorted(unique.values(), key=lambda item: (item.category, str(item.path))), kept


def _within_allowed_roots(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        root_resolved = root.resolve()
        try:
            path.resolve().relative_to(root_resolved)
            return True
        except ValueError:
            continue
    return False


def _prune_empty_directories(roots: Iterable[Path]) -> None:
    for root in sorted({candidate.resolve() for candidate in roots}, key=lambda item: len(str(item)), reverse=True):
        if not root.exists() or not root.is_dir():
            continue

        child_dirs = [path for path in root.rglob("*") if path.is_dir()]
        for directory in sorted(child_dirs, key=lambda item: len(str(item)), reverse=True):
            try:
                if not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                continue


def delete_targets(targets: list[DeletionTarget], *, allowed_roots: Iterable[Path], logger_name: str = "reset_pipeline_state") -> tuple[int, list[str]]:
    logger = get_logger(logger_name)
    deleted = 0
    warnings: list[str] = []

    allowed = [root.resolve() for root in allowed_roots]
    for target in targets:
        if not _within_allowed_roots(target.path, allowed):
            warnings.append(f"SKIP outside allowed roots: {target.path}")
            continue
        try:
            target.path.unlink(missing_ok=True)
            deleted += 1
        except OSError as exc:
            warnings.append(f"SKIP failed delete {target.path}: {exc}")
            logger.debug("Delete failed for %s", target.path, exc_info=exc)

    _prune_empty_directories(allowed)

    return deleted, warnings


def summarize(targets: list[DeletionTarget]) -> str:
    by_category: dict[str, tuple[int, int]] = {}
    for target in targets:
        count, size_bytes = by_category.get(target.category, (0, 0))
        by_category[target.category] = (count + 1, size_bytes + target.size_bytes)

    lines = []
    for category in sorted(by_category):
        count, size_bytes = by_category[category]
        lines.append(f"- {category}: {count} Datei(en), ~{size_bytes / (1024 * 1024):.2f} MiB")
    return "\n".join(lines) if lines else "- Keine Kandidaten gefunden"


def confirm_execute(options: ResetOptions, total: int) -> bool:
    if not options.execute:
        return False
    if options.yes:
        return True
    if not sys.stdin.isatty():
        print("--execute ohne --yes in non-interactive Umgebung nicht erlaubt.")
        return False

    answer = input(f"{total} Dateien löschen. Fortfahren? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def main() -> int:
    args = parse_args()
    try:
        options = parse_options(args)
    except ValueError as exc:
        print(str(exc))
        return 2

    paths = load_reset_paths(PROJECT_ROOT)
    targets, kept_notes = collect_targets(paths, options)

    print(f"Modus: {'EXECUTE' if options.execute else 'DRY-RUN'}")
    print(f"Scopes: {', '.join(options.scopes)}")
    print("Kandidaten je Kategorie:")
    print(summarize(targets))

    if targets:
        print("Identifizierte Pfade:")
        for target in targets:
            print(f"  - [{target.category}] {target.path}")

    print("Bewusst behalten:")
    for note in kept_notes:
        print(f"  - {note}")

    deleted = 0
    warnings: list[str] = []
    if options.execute:
        if not confirm_execute(options, len(targets)):
            print("Abbruch: kein Löschvorgang durchgeführt.")
            return 2

        allowed_roots = {
            paths.audit_root,
            paths.anythingllm_root,
            paths.confluence_staging_root,
            paths.scraping_staging_root,
            paths.jira_staging_root,
            paths.processed_root,
            paths.confluence_transform_manifest_root,
            paths.jira_transform_manifest_root,
            paths.ingestion_manifest_root,
            paths.domains_root,
            paths.confluence_publish_manifest_root,
            paths.reports_root,
            paths.logs_root,
            paths.scripts_logs_root,
            paths.scipts_logs_root,
            paths.index_root,
        }
        deleted, warnings = delete_targets(targets, allowed_roots=allowed_roots)

    print(f"Tatsächlich gelöscht: {deleted} Datei(en)")
    if warnings:
        print("Warnungen:")
        for warning in warnings:
            print(f"  - {warning}")

    print(
        "Hinweis: Für einen echten Full Reset bitte zusätzlich den AnythingLLM-Workspace im "
        "AnythingLLM-UI löschen, sonst können dort noch hochgeladene Dokumente/Vektoren liegen bleiben."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
