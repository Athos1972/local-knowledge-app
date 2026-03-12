from __future__ import annotations

from pathlib import Path
import types

from transformers.markitdown_transformer import MarkItDownTransformer


class _FakeResult:
    def __init__(self, text_content: str):
        self.text_content = text_content


class _FakeMarkItDown:
    def convert(self, _path: str):
        return _FakeResult("# converted")


def test_can_handle_supported_extensions() -> None:
    transformer = MarkItDownTransformer()
    assert transformer.can_handle(Path("doc.pdf"))
    assert transformer.can_handle(Path("sheet.xlsx"))
    assert transformer.can_handle(Path("page.html"))
    assert not transformer.can_handle(Path("archive.zip"))


def test_transform_success_with_mocked_markitdown(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "file.pdf"
    source.write_text("dummy", encoding="utf-8")

    fake_module = types.SimpleNamespace(MarkItDown=_FakeMarkItDown)
    monkeypatch.setitem(__import__("sys").modules, "markitdown", fake_module)

    transformer = MarkItDownTransformer()
    result = transformer.transform(source)

    assert result.success is True
    assert "converted" in result.markdown
    assert result.metadata["file_name"] == "file.pdf"
