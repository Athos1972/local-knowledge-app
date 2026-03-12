from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .markitdown_transformer import MarkItDownTransformer


@dataclass(slots=True)
class TransformRouter:
    """Routes file paths to matching transformer adapters."""

    transformers: list[object] = field(default_factory=lambda: [MarkItDownTransformer()])

    def resolve(self, path: Path) -> object | None:
        for transformer in self.transformers:
            can_handle = getattr(transformer, "can_handle", None)
            if callable(can_handle) and can_handle(path):
                return transformer
        return None

    def can_transform(self, path: Path) -> bool:
        return self.resolve(path) is not None
