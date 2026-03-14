from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TerminologyRelation:
    relation_type: str
    target_id: str


@dataclass(slots=True)
class TerminologyTerm:
    term_id: str
    canonical: str
    label: str
    description: str
    term_class: str
    aliases: list[str] = field(default_factory=list)
    relations: list[TerminologyRelation] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    annotate_policy: str = "first_occurrence"
    block_policy: str = "include"
    case_sensitive: bool = False
    priority: int = 100


@dataclass(slots=True)
class SourceMode:
    mode: str
    candidates_enabled: bool = False


@dataclass(slots=True)
class TerminologyResult:
    text: str
    terms_found: list[str] = field(default_factory=list)
    annotations_applied: int = 0
    block_added: bool = False
