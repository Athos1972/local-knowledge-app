from __future__ import annotations

from pathlib import Path

from local_knowledge_app.transformers.router import TransformRouter


def test_router_resolves_markitdown_for_supported_file() -> None:
    router = TransformRouter()
    transformer = router.resolve(Path("abc.docx"))
    assert transformer is not None
    assert getattr(transformer, "name") == "markitdown"


def test_router_returns_none_for_unsupported_file() -> None:
    router = TransformRouter()
    assert router.resolve(Path("archive.zip")) is None
