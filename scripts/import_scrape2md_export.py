from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processing.scrape2md_importer import ImportConfig, load_import_config, run_import


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importiert scrape2md-Exporte in die lokale Domainstruktur.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Pfad zur TOML-Konfiguration.",
    )
    parser.add_argument("--export-root", type=Path, help="Override für source.export_root")
    parser.add_argument("--source-key", type=str, help="Override für source.source_key")
    parser.add_argument("--knowledge-root", type=Path, help="Override für target.knowledge_root")
    parser.add_argument("--target-subpath", type=Path, help="Override für target.target_subpath")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, keine Dateien schreiben")
    parser.add_argument("--overwrite", action="store_true", help="Existierende Dateien überschreiben")
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Existierende Dateien nicht überschreiben",
    )
    return parser


def _apply_overrides(config: ImportConfig, args: argparse.Namespace) -> ImportConfig:
    if args.export_root is not None:
        config.source.export_root = args.export_root
    if args.source_key is not None:
        config.source.source_key = args.source_key
    if args.knowledge_root is not None:
        config.target.knowledge_root = args.knowledge_root
    if args.target_subpath is not None:
        config.target.target_subpath = args.target_subpath
    if args.dry_run:
        config.behavior.dry_run = True
    if args.overwrite:
        config.behavior.overwrite = True
    if args.no_overwrite:
        config.behavior.overwrite = False
    return config


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.config is None:
        parser.error("--config ist erforderlich")

    config = load_import_config(args.config)
    config = _apply_overrides(config, args)

    stats = run_import(config)

    print("Import abgeschlossen")
    print(f"- Importiert: {stats.imported}")
    print(f"- Aktualisiert: {stats.updated}")
    print(f"- Übersprungen: {stats.skipped}")
    print(f"- Fehler: {len(stats.errors)}")

    if stats.errors:
        print("Fehlerliste:")
        for err in stats.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
