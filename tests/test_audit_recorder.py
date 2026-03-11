from pathlib import Path

from processing.audit.models import AuditStage, ReasonCode
from processing.audit.recorder import AuditRecorder, PipelineRunContext
from processing.audit.repository import AuditRepository


def test_stage_context_auto_ok(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    run = PipelineRunContext(repository, source_type="filesystem", mode="test")
    recorder = AuditRecorder(repository)

    with recorder.stage(
        run_id=run.run_id,
        source_type="filesystem",
        stage=AuditStage.TRANSFORM,
        document_id="doc-1",
        document_title="Titel",
    ) as event:
        event.event.output_count = 42

    rows = repository.query("SELECT stage, status, output_count FROM document_stage_events")
    assert len(rows) == 1
    assert rows[0]["stage"] == AuditStage.TRANSFORM
    assert rows[0]["status"] == "ok"
    assert rows[0]["output_count"] == 42


def test_stage_context_error_and_reraise(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    run = PipelineRunContext(repository, source_type="filesystem", mode="test")
    recorder = AuditRecorder(repository)

    try:
        with recorder.stage(
            run_id=run.run_id,
            source_type="filesystem",
            stage=AuditStage.CHUNK,
            document_id="doc-2",
        ):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    rows = repository.query("SELECT status, reason_code, message FROM document_stage_events")
    assert rows[0]["status"] == "error"
    assert rows[0]["reason_code"] == ReasonCode.UNKNOWN_EXCEPTION
    assert "boom" in rows[0]["message"]
