"""Configurable domain mapping for local document sources."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(slots=True)
class DomainMappingRule:
    """One mapping rule based on a glob-like relative path match."""

    match: str
    domain: str


class DomainMapper:
    """Maps source-relative paths to domain names using configured rules."""

    def __init__(self, rules: list[DomainMappingRule], fallback_domain: str = "misc_documents"):
        self.rules = rules
        self.fallback_domain = fallback_domain

    @classmethod
    def from_config(cls, data: list[dict[str, object]] | None, fallback_domain: str = "misc_documents") -> "DomainMapper":
        rules: list[DomainMappingRule] = []
        for item in data or []:
            match = str(item.get("match", "")).strip()
            domain = str(item.get("domain", "")).strip()
            if not match or not domain:
                continue
            rules.append(DomainMappingRule(match=match, domain=domain))
        return cls(rules=rules, fallback_domain=fallback_domain)

    def resolve_domain(self, relative_path: Path) -> str:
        """Resolve the domain for a path relative to documents input root."""
        candidate = relative_path.as_posix()
        for rule in self.rules:
            if fnmatch(candidate, rule.match):
                return rule.domain
        return self.fallback_domain
