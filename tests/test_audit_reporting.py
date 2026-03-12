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
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="filter", status="skipped", reason_code="unchanged_incremental", document_id="2", document_title="B"))
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="transform", status="warning", reason_code="unsupported_macro", document_id="1", document_title="A"))
    repository.insert_event(AuditEvent(run_id="run-1", source_type="confluence", source_instance="WSTW", stage="chunk", status="skipped", reason_code="no_chunks_created", document_id="1", document_title="A"))

    service = AuditReportService(repository)
    report = service.build_report(ReportFilters(report_date=datetime(2026, 3, 11, tzinfo=UTC).date()))

    assert len(report["runs"]) == 1
    assert report["stage_stats"]["transform"]["warning"] == 1
    assert report["stage_stats"]["chunk"]["skipped"] == 1
    assert report["funnel"]["run-1"]["unchanged_skipped"] == 1
    assert report["funnel"]["run-1"]["transformed_ok"] == 1
    assert report["reason_codes"][0]["reason_code"] in {"unsupported_macro", "no_chunks_created", "unchanged_incremental"}
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


def test_drilldown_contains_reason_and_lengths(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path / "audit.sqlite")
    run = PipelineRun(run_id="run-3", started_at=datetime(2026, 3, 11, 12, 0, tzinfo=UTC).isoformat(), source_type="filesystem", mode="delta")
    repository.upsert_run(run)
    repository.insert_event(
        AuditEvent(
            run_id="run-3",
            source_type="filesystem",
            source_instance="local",
            stage="transform",
            status="error",
            reason_code="transform_exception",
            message="broken",
            document_id="doc-1",
            document_title="Doc 1",
            input_count=100,
            output_count=0,
            extra_json={"changed_flag": True, "is_dirty": True},
        )
    )

    rows = AuditReportService(repository).build_drilldown(ReportFilters(report_date=datetime(2026, 3, 11, tzinfo=UTC).date(), run_id="run-3"))
    assert len(rows) == 1
    assert rows[0]["reason_code"] == "transform_exception"
    assert rows[0]["raw_text_length"] == 100
    assert rows[0]["changed_flag"] is True
