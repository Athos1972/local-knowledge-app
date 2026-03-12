"""Compatibility wrappers for legacy local_knowledge_app.pipelines imports."""

from pipelines.domain_mapping import MapRunConfig, run_mapping
from pipelines.scraping_transform import TransformRunConfig, run_transform

__all__ = ["MapRunConfig", "run_mapping", "TransformRunConfig", "run_transform"]
