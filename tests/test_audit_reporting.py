from datetime import UTC, datetime
from pathlib import Path

from processing.audit.models import AuditEvent, PipelineRun
from processing.audit.reporting import AuditReportService, ReportFilters
from processing.audit.repository import AuditRepository


def test_reporting_aggregates_stage_status_and_reasons(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    started = datetime(2026, 3, 11, 10, 0, tzinfo=UTC).isoformat()
    run = PipelineRun(run_id="run-1", started_at=started, source_type="confluence", source_instance="WSTW", mode="full", status="finished")
    repository.upsert_run(run)

    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="discover", status="ok", document_id="1", document_title="A"))
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="load", status="ok", document_id="1", document_title="A"))
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="transform", status="warning", reason_code="unsupported_macro", document_id="1", document_title="A"))
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="chunk", status="skipped", reason_code="no_chunks_created", document_id="1", document_title="A"))

    service = AuditReportService(repository)
    report = service.build_report(ReportFilters(report_date=datetime(2026, 3, 11, tzinfo=UTC).date()))

    assert len(report["runs"]) == 1
    assert report["stage_stats"]["transform"]["warning"] == 1
    assert report["stage_stats"]["chunk"]["skipped"] == 1
    assert report["reason_codes"][0]["reason_code"] in {"unsupported_macro", "no_chunks_created"}
    assert report["drop_off"][0]["drop"] >= 0


def test_reporting_problem_document_contains_last_non_ok_status(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    run = PipelineRun(run_id="run-2", started_at=datetime(2026, 3, 11, 11, 0, tzinfo=UTC).isoformat(), source_type="filesystem", mode="delta")
    repository.upsert_run(run)

    repository.insert_event(AuditEvent(run_id="run-2", source_type="filesystem", source_instance="local", stage="load", status="ok", document_id="doc-7", document_title="Doc"))
    repository.insert_event(AuditEvent(run_id="run-2", source_type="filesystem", source_instance="local", stage="transform", status="error", reason_code="transform_exception", message="kaputt", document_id="doc-7", document_title="Doc"))

    report = AuditReportService(repository).build_report(ReportFilters(report_date=datetime(2026, 3, 11, tzinfo=UTC).date()))
    assert report["problem_documents"][0]["document_id"] == "doc-7"
    assert report["problem_documents"][0]["status"] == "error"
