from datetime import UTC, datetime
from pathlib import Path

from processing.audit.models import AuditEvent, PipelineRun
from processing.audit.repository import AuditRepository


def test_repository_persists_run_and_event(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    run = PipelineRun(
        run_id="run-1",
        started_at=datetime.now(UTC).isoformat(),
        source_type="filesystem",
        mode="full",
    )
    repository.upsert_run(run)
    repository.insert_event(
        AuditEvent(
            run_id="run-1",
            source_type="filesystem",
            source_instance="instance-a",
            document_id="doc-a",
            document_title="Doc A",
            stage="load",
            status="ok",
            output_count=100,
        )
    )

    runs = repository.query("SELECT run_id, source_type FROM pipeline_runs")
    events = repository.query("SELECT document_id, stage, status, output_count FROM document_stage_events")

    assert runs[0]["run_id"] == "run-1"
    assert events[0]["document_id"] == "doc-a"
    assert events[0]["output_count"] == 100
