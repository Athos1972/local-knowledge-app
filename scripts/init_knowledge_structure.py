from pathlib import Path
import datetime
import sys


ROOT_DIRS = [
    "inbox",
    "domains",
    "exports/confluence",
    "exports/jira",
    "exports/git",
    "exports/mail",
    "exports/scraping",
    "staging/raw",
    "staging/normalized",
    "staging/rejected",
    "processed/documents",
    "processed/chunks",
    "processed/metadata",
    "index/vectorstore",
    "index/cache",
    "system/config",
    "system/manifests",
    "system/source_registry",
    "system/run_logs",
    "archive/old_exports",
    "archive/retired_sources",
]

SAP_PLATFORM_DIRS = [
    "domains/sap/platform/mcp/cap",
    "domains/sap/platform/mcp/ui5",
    "domains/sap/platform/mcp/fiori",
    "domains/sap/platform/mcp/sap_docs",
    "domains/sap/platform/git",
    "domains/sap/platform/reference/sap_docs",
    "domains/sap/platform/reference/ebutilities",
    "domains/sap/platform/reference/training",
    "domains/sap/platform/architecture/clean_core",
    "domains/sap/platform/architecture/event_mesh",
    "domains/sap/platform/architecture/integration_patterns",
    "domains/sap/platform/notes",
]

OTHER_DOMAIN_DIRS = [
    "domains/cats/medical",
    "domains/cats/appointments",
    "domains/cats/food",
    "domains/cats/charity",
    "domains/cats/notes",
    "domains/real_estate",
    "domains/investments",
    "domains/ideas/notes",
]

PROJECT_SUBDIRS = [
    "confluence",
    "jira",
    "git",
    "documents",
    "meetings",
    "notes",
    "reference",
]


README_TEMPLATE = """# {title}

Dieser Ordner ist Teil des lokalen Wissenssystems.

## Zweck

Beschreibe hier kurz:
- welche Inhalte hier liegen
- wie sie strukturiert sind
- wie sie verwendet werden

## Hinweise

- Originaldaten und verarbeitete Daten nicht vermischen
- Markdown für eigene Notizen bevorzugen
"""


def create_dir_with_readme(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    readme_path = path / "README.md"
    if not readme_path.exists():
        title = path.name.replace("_", " ").replace("-", " ").title()
        readme_path.write_text(README_TEMPLATE.format(title=title), encoding="utf-8")


def create_paths(base_path: Path, relative_paths: list[str]) -> None:
    for rel in relative_paths:
        create_dir_with_readme(base_path / rel)


def create_project_structure(base_path: Path, customer: str, project: str) -> None:
    project_root = base_path / "domains" / "sap" / "customers" / customer / "projects" / project
    create_dir_with_readme(project_root)

    for subdir in PROJECT_SUBDIRS:
        create_dir_with_readme(project_root / subdir)


def create_customer_base(base_path: Path, customer: str) -> None:
    customer_root = base_path / "domains" / "sap" / "customers" / customer
    create_dir_with_readme(customer_root)
    create_dir_with_readme(customer_root / "projects")
    create_dir_with_readme(customer_root / "overview")
    create_dir_with_readme(customer_root / "architecture")


def create_inbox_month(base_path: Path) -> None:
    today = datetime.date.today()
    inbox_month = base_path / "inbox" / today.strftime("%Y-%m")
    create_dir_with_readme(inbox_month)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/init_knowledge_structure.py <base_path> [customer] [project]")
        print("")
        print("Example:")
        print("  python scripts/init_knowledge_structure.py ~/data/local-knowledge-data stadtwerke s4_transformation")
        sys.exit(1)

    base_path = Path(sys.argv[1]).expanduser()
    customer = sys.argv[2] if len(sys.argv) >= 3 else "stadtwerke"
    project = sys.argv[3] if len(sys.argv) >= 4 else "projekt_1"

    create_dir_with_readme(base_path)

    create_paths(base_path, ROOT_DIRS)
    create_paths(base_path, SAP_PLATFORM_DIRS)
    create_paths(base_path, OTHER_DOMAIN_DIRS)

    create_customer_base(base_path, customer)
    create_project_structure(base_path, customer, project)
    create_inbox_month(base_path)

    print(f"Struktur wurde angelegt unter: {base_path}")
    print(f"Kunde:  {customer}")
    print(f"Projekt: {project}")


if __name__ == "__main__":
    main()