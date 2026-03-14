from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import logging
from pathlib import Path

from processing.terminology.loader import TerminologyLoader


logger = logging.getLogger(__name__)

CANDIDATE_COLUMNS = [
    "source_type",
    "term",
    "count",
    "first_seen_file",
    "last_seen_file",
    "example_context",
    "already_known",
    "suggested_action",
    "selected_term_id",
    "reviewer_status",
    "reviewer_note",
]


@dataclass(slots=True)
class CandidateRow:
    source_type: str
    term: str
    count: int
    first_seen_file: str
    last_seen_file: str
    example_context: str
    already_known: str = "false"
    suggested_action: str = "needs_review"
    selected_term_id: str = ""
    reviewer_status: str = "open"
    reviewer_note: str = ""


class TerminologyCandidateReviewService:
    """Enriches candidate rows with reviewer hints while preserving reviewer input."""

    def __init__(self, config_root: Path, candidates_csv: Path) -> None:
        self._config_root = config_root
        self._candidates_csv = candidates_csv

    def enrich(self) -> list[CandidateRow]:
        loader = TerminologyLoader(self._config_root)
        config = loader.load()

        known_to_term_id: dict[str, str] = {}
        for term in config.terms_by_id.values():
            known_to_term_id[term.canonical.lower()] = term.term_id
            for alias in term.aliases:
                known_to_term_id[alias.lower()] = term.term_id

        rows = self._read_rows()
        enriched: list[CandidateRow] = []
        for row in rows:
            known_term_id = known_to_term_id.get(row.term.lower())
            if known_term_id:
                row.already_known = "true"
                row.suggested_action = "add_alias"
                row.selected_term_id = row.selected_term_id or known_term_id
                row.reviewer_status = row.reviewer_status if row.reviewer_status != "open" else "done"
            elif row.count >= 3:
                row.suggested_action = "new_term"
            else:
                row.suggested_action = "needs_review"
            enriched.append(row)

        self._write_rows(enriched)
        logger.info("Terminology candidates reviewed: rows=%s known=%s", len(enriched), sum(1 for row in enriched if row.already_known == "true"))
        return enriched

    def _read_rows(self) -> list[CandidateRow]:
        """Load candidate rows from CSV and tolerate older files without new columns."""
        if not self._candidates_csv.exists():
            return []
        with self._candidates_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows: list[CandidateRow] = []
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

    def _write_rows(self, rows: list[CandidateRow]) -> None:
        """Rewrite the candidates CSV using the canonical column layout."""
        self._candidates_csv.parent.mkdir(parents=True, exist_ok=True)
        with self._candidates_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANDIDATE_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
