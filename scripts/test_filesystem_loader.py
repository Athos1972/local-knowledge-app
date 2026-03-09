from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sources.filesystem.filesystem_loader import FilesystemLoader

loader = FilesystemLoader(
    Path("~/local-knowledge-data/domains").expanduser()
)

docs = loader.load()

print("Dokumente geladen:", len(docs))

for d in docs[:5]:
    print(f"Title: {d.title}")
    print(f"Metadata: {d.metadata}")
    print(f"PATH: {d.path}")
    print("-" * 80)