from __future__ import annotations

import csv
import fnmatch
import logging
from collections import Counter
from pathlib import Path
import re

from processing.terminology.candidates import CANDIDATE_COLUMNS, CandidateRow
from processing.terminology.loader import TerminologyLoader, TerminologySettings, resolve_terminology_file_names
from processing.terminology.models import SourceMode, TerminologyResult, TerminologyTerm


logger = logging.getLogger(__name__)


class TerminologyService:
    """Apply terminology enrichment and maintain aggregated candidate reporting.

    Candidate rows are aggregated by ``(source_type, normalized_term)`` across runs,
    merged with any existing ``reports/terminology_candidates.csv`` content, and keep
    reviewer columns stable.
    """

    def __init__(self, config_root: Path | None = None, reports_root: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self._config_root = config_root or (root / "config" / "terminology")
        self._reports_root = reports_root or (root / "reports")

        self._settings = TerminologySettings(candidate_patterns=[r"\b[A-ZÄÖÜ][A-ZÄÖÜ0-9\-]{2,}\b"])
        self._source_modes: dict[str, SourceMode] = {}
        self._terms_by_id: dict[str, TerminologyTerm] = {}
        self._candidate_exclude_patterns: list[str] = []
        self._file_names = resolve_terminology_file_names()
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

        working_text = text
        mentions: dict[str, list[re.Match[str]]] = {}
        if scoped_terms:
            mentions = self._match_terms(working_text, scoped_terms)

        annotations = 0
        if scoped_terms and source_mode.mode == "annotate_and_block":
            working_text, annotations = self._annotate_first_occurrences(working_text, mentions)

        block_added = False
        if scoped_terms and source_mode.mode in {"annotate_and_block", "block_only"}:
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
            self._candidate_exclude_patterns = self._load_candidate_exclude_patterns()
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
        """Merge current document candidates into the aggregated candidate CSV."""
        known = {m.group(0).lower() for matches in mentions.values() for m in matches}
        candidate_counts: Counter[str] = Counter()
        candidate_examples: dict[str, str] = {}
        excluded_terms = 0

        for pattern in self._settings.candidate_patterns or []:
            for match in re.finditer(pattern, text):
                candidate = match.group(0).strip()
                if not candidate:
                    continue
                if candidate.lower() in known:
                    continue
                if self._is_excluded_candidate(candidate):
                    excluded_terms += 1
                    logger.debug("Terminology candidate excluded: source=%s term=%s", source_type, candidate)
                    continue
                candidate_counts[candidate] += 1
                candidate_examples.setdefault(candidate, self._extract_context(text, match.start(), match.end()))

        if not candidate_counts:
            logger.info(
                "terminology candidates updated: source=%s new_terms=0 merged_terms=0 excluded_terms=%s csv_rows=%s",
                source_type,
                excluded_terms,
                len(self._read_candidate_rows(self._reports_root / 'terminology_candidates.csv')),
            )
            return

        self._reports_root.mkdir(parents=True, exist_ok=True)
        path = self._reports_root / "terminology_candidates.csv"
        existing_rows = self._read_candidate_rows(path)
        existing_index: dict[tuple[str, str], CandidateRow] = {
            (row.source_type, self._normalize_candidate_term(row.term)): row for row in existing_rows
        }

        new_terms = 0
        merged_terms = 0
        for term, count in sorted(candidate_counts.items()):
            key = (source_type, self._normalize_candidate_term(term))
            row = existing_index.get(key)
            if row is None:
                new_terms += 1
                row = CandidateRow(
                    source_type=source_type,
                    term=term,
                    count=count,
                    first_seen_file=source_ref,
                    last_seen_file=source_ref,
                    example_context=candidate_examples.get(term, ""),
                )
                existing_rows.append(row)
                existing_index[key] = row
                continue

            merged_terms += 1
            old_count = row.count
            row.count += count
            if not row.first_seen_file and source_ref:
                row.first_seen_file = source_ref
            if source_ref:
                row.last_seen_file = source_ref
            if not row.example_context:
                row.example_context = candidate_examples.get(term, "")
            logger.debug(
                "Terminology candidate merged: source=%s term=%s old_count=%s new_count=%s",
                source_type,
                term,
                old_count,
                row.count,
            )

        existing_rows.sort(key=lambda row: (row.source_type, self._normalize_candidate_term(row.term), row.term))
        self._write_candidate_rows(path, existing_rows)
        logger.info(
            "terminology candidates updated: source=%s new_terms=%s merged_terms=%s excluded_terms=%s csv_rows=%s",
            source_type,
            new_terms,
            merged_terms,
            excluded_terms,
            len(existing_rows),
        )

    def _extract_context(self, text: str, start: int, end: int) -> str:
        left = max(0, start - 40)
        right = min(len(text), end + 40)
        return " ".join(text[left:right].split())

    def _read_candidate_rows(self, path: Path) -> list[CandidateRow]:
        """Read candidate CSV rows and support legacy files without all columns."""
        if not path.exists():
            return []
        rows: list[CandidateRow] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for record in reader:
                rows.append(
                    CandidateRow(
                        source_type=str(record.get("source_type", "")),
                        term=str(record.get("term", "")),
                        count=int(record.get("count", "0") or 0),
                        first_seen_file=str(record.get("first_seen_file", "")),
                        last_seen_file=str(record.get("last_seen_file", "")),
                        example_context=str(record.get("example_context", "")),
                        already_known=str(record.get("already_known", "false") or "false"),
                        suggested_action=str(record.get("suggested_action", "needs_review") or "needs_review"),
                        selected_term_id=str(record.get("selected_term_id", "")),
                        reviewer_status=str(record.get("reviewer_status", "open") or "open"),
                        reviewer_note=str(record.get("reviewer_note", "")),
                    )
                )
        return rows

    def _write_candidate_rows(self, path: Path, rows: list[CandidateRow]) -> None:
        """Write the aggregated candidate rows using canonical headers."""
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANDIDATE_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "source_type": row.source_type,
                        "term": row.term,
                        "count": row.count,
                        "first_seen_file": row.first_seen_file,
                        "last_seen_file": row.last_seen_file,
                        "example_context": row.example_context,
                        "already_known": row.already_known,
                        "suggested_action": row.suggested_action,
                        "selected_term_id": row.selected_term_id,
                        "reviewer_status": row.reviewer_status,
                        "reviewer_note": row.reviewer_note,
                    }
                )

    def _normalize_candidate_term(self, term: str) -> str:
        """Normalize candidate terms for aggregation without changing visible CSV values."""
        normalized = re.sub(r"\s+", " ", term.strip())
        return normalized.lower()

    def _load_candidate_exclude_patterns(self) -> list[str]:
        """Load candidate exclude patterns from YAML (case-insensitive wildcard `*`)."""
        path = self._config_root / self._file_names.candidate_exclude
        if not path.exists():
            return []

        try:
            import yaml

            with path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            entries = raw.get("candidate_exclude", []) if isinstance(raw, dict) else []
            if not isinstance(entries, list):
                logger.warning("Invalid terminology candidate exclude config: %s", path)
                return []
            patterns = [str(entry).strip() for entry in entries if str(entry).strip()]
            logger.debug("Terminology candidate exclude patterns loaded: count=%s", len(patterns))
            return patterns
        except Exception as exc:  # pragma: no cover - defensive runtime handling
            logger.warning("Failed to load terminology candidate exclude patterns: %s", exc)
            return []

    def _is_excluded_candidate(self, candidate: str) -> bool:
        """Return True when candidate matches any configured wildcard exclude."""
        lowered = candidate.lower()
        for pattern in self._candidate_exclude_patterns:
            if fnmatch.fnmatch(lowered, pattern.lower()):
                return True
        return False
