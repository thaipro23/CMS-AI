from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicSyncRun,
    AcademicTeacherReportJob,
)
from app.schemas.academic import AcademicAPSyncIn
from app.services.academic.ap_sync import AcademicAPSyncWorkflowService


def test_daily_pipeline_attempt_columns_are_nullable_and_indexed():
    bulk_parent = AcademicBulkOperationJob.__table__.c.parent_job_id
    sync_key = AcademicSyncRun.__table__.c.idempotency_key
    report_parent = AcademicTeacherReportJob.__table__.c.parent_job_id
    report_key = AcademicTeacherReportJob.__table__.c.idempotency_key

    assert bulk_parent.nullable is True
    assert bulk_parent.index is True
    assert sync_key.nullable is True
    assert sync_key.unique is True
    assert sync_key.index is True
    assert report_parent.nullable is True
    assert report_parent.index is True
    assert report_key.nullable is True
    assert report_key.unique is True
    assert report_key.index is True


def test_ap_enqueue_reuses_the_exact_attempt_key_before_foreign_active_work(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AcademicSyncRun.__table__.create(engine)
    with Session(engine) as db:
        exact = AcademicSyncRun(
            id="run-exact",
            source="ap",
            mode="api_all_job",
            status="completed",
            requested_by="scheduler",
            term_name="Fall 2026",
            branch="poly",
            idempotency_key="ap-stage:root-1:poly:0",
            counters_json={"daily_pipeline": {"round": 0}},
        )
        foreign = AcademicSyncRun(
            id="run-foreign",
            source="ap",
            mode="api_all_job",
            status="running",
            requested_by="operator",
            term_name="Fall 2026",
            branch="poly",
            idempotency_key="manual:foreign",
            counters_json={},
        )
        db.add_all([exact, foreign])
        db.commit()

        service = AcademicAPSyncWorkflowService(db)
        monkeypatch.setattr(
            service,
            "_effective_selected_subject_codes",
            lambda **kwargs: (["DOM101"], {"selected_subject_codes": ["DOM101"]}),
        )
        result = service.enqueue_sync_from_ap_job(
            AcademicAPSyncIn(
                term_name="Fall 2026",
                sync_scope="all",
                campuses=["hn"],
                branch="poly",
            ),
            user=UserContext(
                user_id="scheduler",
                username="scheduler",
                email="scheduler@example.test",
                role="admin",
                permissions={"academic.manage"},
            ),
            idempotency_key="ap-stage:root-1:poly:0",
            run_metadata={"root_job_id": "root-1", "round": 0},
        )

        assert result["sync_run"].id == "run-exact"
        assert db.query(AcademicSyncRun).count() == 2
    engine.dispose()
