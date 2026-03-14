from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path
import re
from processing.terminology.candidates import CANDIDATE_COLUMNS
from processing.terminology.loader import TerminologyLoader, TerminologySettings
from processing.terminology.models import SourceMode, TerminologyResult, TerminologyTerm


logger = logging.getLogger(__name__)


class TerminologyService:
    def __init__(self, config_root: Path | None = None, reports_root: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self._config_root = config_root or (root / "config" / "terminology")
        self._reports_root = reports_root or (root / "reports")

        self._settings = TerminologySettings(candidate_patterns=[r"\b[A-ZÄÖÜ][A-ZÄÖÜ0-9\-]{2,}\b"])
        self._source_modes: dict[str, SourceMode] = {}
        self._terms_by_id: dict[str, TerminologyTerm] = {}
        self._loaded = False

    def apply_to_text(self, text: str, source_type: str, *, source_ref: str = "") -> TerminologyResult:
        if not self._ensure_loaded():
            logger.info("Terminology skipped: source=%s reason=config_unavailable", source_type)
            return TerminologyResult(text=text)

        if not self._settings.enabled:
            logger.info("Terminology skipped: source=%s reason=disabled", source_type)
            return TerminologyResult(text=text)

        source_mode = self._source_modes.get(source_type)
        if source_mode is None or source_mode.mode == "off":
            logger.info("Terminology skipped: source=%s reason=disabled", source_type)
            return TerminologyResult(text=text)

        scoped_terms = self._terms_for_source(source_type)
        if not scoped_terms:
            logger.info("Terminology skipped: source=%s reason=no_terms", source_type)
            return TerminologyResult(text=text)

        working_text = text
        mentions = self._match_terms(working_text, scoped_terms)

        annotations = 0
        if source_mode.mode == "annotate_and_block":
            working_text, annotations = self._annotate_first_occurrences(working_text, mentions)

        block_added = False
        if source_mode.mode in {"annotate_and_block", "block_only"}:
            working_text, block_added = self._append_terminology_block(working_text, mentions)

        if self._settings.candidate_detection_enabled and source_mode.candidates_enabled:
            self._update_candidate_report(text, source_type, source_ref, mentions)

        logger.info(
            "Terminology applied: source=%s terms_found=%s annotations=%s block_added=%s",
            source_type,
            len(mentions),
            annotations,
            "yes" if block_added else "no",
        )

        return TerminologyResult(
            text=working_text,
            terms_found=[term_id for term_id in mentions],
            annotations_applied=annotations,
            block_added=block_added,
        )

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True

        try:
            config = TerminologyLoader(self._config_root).load()
            self._settings = config.settings
            self._source_modes = config.source_modes
            self._terms_by_id = config.terms_by_id
            self._loaded = True
            return True
        except Exception as exc:  # pragma: no cover - defensive runtime handling
            logger.warning("Terminology disabled due to configuration error: %s", exc)
            self._loaded = False
            return False

    def _terms_for_source(self, source_type: str) -> dict[str, TerminologyTerm]:
        return {
            term_id: term
            for term_id, term in self._terms_by_id.items()
            if not term.applies_to or source_type in term.applies_to
        }

    def _match_terms(self, text: str, terms: dict[str, TerminologyTerm]) -> dict[str, list[re.Match[str]]]:
        matches: dict[str, list[re.Match[str]]] = {}
        for term_id, term in terms.items():
            term_matches = self._match_term(text, term)
            if term_matches:
                matches[term_id] = term_matches
                logger.debug("Terminology match: term=%s count=%s", term_id, len(term_matches))
        return dict(sorted(matches.items(), key=lambda item: item[1][0].start()))

    def _match_term(self, text: str, term: TerminologyTerm) -> list[re.Match[str]]:
        variants = [term.canonical, *term.aliases]
        found: list[re.Match[str]] = []
        for variant in sorted(set(v for v in variants if v), key=len, reverse=True):
            flags = 0 if term.case_sensitive or not self._settings.case_insensitive_default else re.IGNORECASE
            pattern = self._variant_pattern(variant)
            found.extend(re.finditer(pattern, text, flags=flags))

        found.sort(key=lambda m: m.start())
        deduped: list[re.Match[str]] = []
        seen_spans: set[tuple[int, int]] = set()
        for match in found:
            span = (match.start(), match.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            deduped.append(match)
        return deduped

    def _variant_pattern(self, variant: str) -> str:
        escaped = re.escape(variant)
        if self._settings.normalize_hyphen_whitespace:
            escaped = re.sub(r"\\\\[\-\\s]+", r"[-\\s]?", escaped)
        return rf"(?<!\w){escaped}(?!\w)"

    def _annotate_first_occurrences(self, text: str, mentions: dict[str, list[re.Match[str]]]) -> tuple[str, int]:
        replacements: list[tuple[int, int, str]] = []
        for term_id, term_mentions in mentions.items():
            term = self._terms_by_id[term_id]
            if term.annotate_policy != "first_occurrence":
                continue
            if term.term_class == "person":
                continue
            first = term_mentions[0]
            replacement = f"{first.group(0)} ({term.label})"
            replacements.append((first.start(), first.end(), replacement))

        if not replacements:
            return text, 0

        replacements.sort(key=lambda item: item[0], reverse=True)
        output = text
        for start, end, replacement in replacements:
            output = output[:start] + replacement + output[end:]
        return output, len(replacements)

    def _append_terminology_block(self, text: str, mentions: dict[str, list[re.Match[str]]]) -> tuple[str, bool]:
        eligible = [
            self._terms_by_id[term_id]
            for term_id in mentions
            if self._terms_by_id[term_id].block_policy != "exclude"
        ]
        if len(eligible) < self._settings.block_min_terms:
            return text, False

        sorted_terms = sorted(
            eligible,
            key=lambda term: (mentions[term.term_id][0].start(), term.priority, term.canonical.lower()),
        )

        lines = ["", "## Terminologie"]
        for term in sorted_terms:
            lines.append(f"- {term.canonical}: {term.label}")
            related_labels = self._related_labels(term)
            if related_labels:
                lines.append(f"  - Verwandte Begriffe: {', '.join(related_labels)}")
            if self._settings.show_aliases_in_block and term.aliases:
                lines.append(f"  - Aliase: {', '.join(term.aliases)}")

        return text.rstrip() + "\n" + "\n".join(lines) + "\n", True

    def _related_labels(self, term: TerminologyTerm) -> list[str]:
        labels: list[str] = []
        for relation in term.relations:
            if relation.relation_type != "related_to":
                continue
            target = self._terms_by_id.get(relation.target_id)
            if target is not None:
                labels.append(target.canonical)
        return labels

    def _update_candidate_report(
        self,
        text: str,
        source_type: str,
        source_ref: str,
        mentions: dict[str, list[re.Match[str]]],
    ) -> None:
        known = {m.group(0).lower() for matches in mentions.values() for m in matches}
        candidate_counts: Counter[str] = Counter()
        candidate_examples: dict[str, str] = {}

        for pattern in self._settings.candidate_patterns or []:
            for match in re.finditer(pattern, text):
                candidate = match.group(0).strip()
                if not candidate:
                    continue
                if candidate.lower() in known:
                    continue
                candidate_counts[candidate] += 1
                candidate_examples.setdefault(candidate, self._extract_context(text, match.start(), match.end()))

        if not candidate_counts:
            return

        self._reports_root.mkdir(parents=True, exist_ok=True)
        path = self._reports_root / "terminology_candidates.csv"
        write_header = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if write_header:
                writer.writerow(CANDIDATE_COLUMNS)
            for term, count in sorted(candidate_counts.items()):
                writer.writerow([source_type, term, count, source_ref, candidate_examples.get(term, ""), "false", "needs_review", "", "open", ""])

    def _extract_context(self, text: str, start: int, end: int) -> str:
        left = max(0, start - 40)
        right = min(len(text), end + 40)
        return " ".join(text[left:right].split())
