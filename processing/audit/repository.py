"""SQLite-Persistenz für Audit-Runs und Stage-Events."""

from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3
from pathlib import Path

from processing.audit.models import AuditEvent, PipelineRun


class AuditRepository:
    """Kapselt Tabellenanlage und Schreib-/Lesezugriffe für Auditdaten."""

    def __init__(self, db_path: Path):
        self.db_path = db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    source_type TEXT NOT NULL,
                    source_instance TEXT,
                    mode TEXT,
                    status TEXT NOT NULL,
                    total_events INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS document_stage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_instance TEXT,
                    document_id TEXT,
                    document_uri TEXT,
                    document_title TEXT,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_code TEXT,
                    message TEXT,
                    input_count INTEGER,
                    output_count INTEGER,
                    chunk_count INTEGER,
                    duration_ms INTEGER,
                    created_at TEXT NOT NULL,
                    extra_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_run_stage ON document_stage_events(run_id, stage);
                CREATE INDEX IF NOT EXISTS idx_events_reason ON document_stage_events(reason_code);
                CREATE INDEX IF NOT EXISTS idx_events_created_at ON document_stage_events(created_at);
                """
            )

    def upsert_run(self, run: PipelineRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs(run_id, started_at, finished_at, source_type, source_instance, mode, status, total_events)
                VALUES (:run_id, :started_at, :finished_at, :source_type, :source_instance, :mode, :status, :total_events)
                ON CONFLICT(run_id) DO UPDATE SET
                    finished_at=excluded.finished_at,
                    status=excluded.status,
                    total_events=excluded.total_events,
                    source_instance=excluded.source_instance,
                    mode=excluded.mode
                """,
                asdict(run),
            )

    def insert_event(self, event: AuditEvent) -> None:
        payload = asdict(event)
        payload["extra_json"] = json.dumps(event.extra_json, ensure_ascii=False) if event.extra_json else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO document_stage_events(
                    run_id, source_type, source_instance, document_id, document_uri, document_title,
                    stage, status, reason_code, message, input_count, output_count, chunk_count,
                    duration_ms, created_at, extra_json
                ) VALUES (
                    :run_id, :source_type, :source_instance, :document_id, :document_uri, :document_title,
                    :stage, :status, :reason_code, :message, :input_count, :output_count, :chunk_count,
                    :duration_ms, :created_at, :extra_json
                )
                """,
                payload,
            )

    def count_events_for_run(self, run_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM document_stage_events WHERE run_id = ?", (run_id,)).fetchone()
        return int(row["c"] if row else 0)

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(sql, params).fetchall()
