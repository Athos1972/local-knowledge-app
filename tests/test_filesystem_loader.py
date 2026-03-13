from pathlib import Path

from sources.filesystem.filesystem_loader import FilesystemLoader


def test_loader_skips_markdown_without_meaningful_content(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("# Nur Header\n\n## Noch ein Header\n", encoding="utf-8")
    (tmp_path / "valid.md").write_text("# Titel\n\nInhalt", encoding="utf-8")

    docs = list(FilesystemLoader(tmp_path).load())

    assert len(docs) == 1
    assert docs[0].metadata["filename"] == "valid.md"
