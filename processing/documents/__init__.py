"""Document transformation components for local Office/PDF-style sources."""

from .domain_mapper import DomainMapper, DomainMappingRule
from .file_loader import DocumentFile, DocumentFileLoader
from .frontmatter import build_document_frontmatter
from .manifest import DocumentTransformRecord, DocumentTransformRunManifest, generate_transform_run_id
from .state import DocumentTransformState, DocumentTransformStateRecord
from .writer import DocumentsTransformWriter, RenderedDocument

__all__ = [
    "DocumentFile",
    "DocumentFileLoader",
    "DomainMapper",
    "DomainMappingRule",
    "DocumentTransformRecord",
    "DocumentTransformRunManifest",
    "DocumentTransformState",
    "DocumentTransformStateRecord",
    "DocumentsTransformWriter",
    "RenderedDocument",
    "build_document_frontmatter",
    "generate_transform_run_id",
]
