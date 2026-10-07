from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicClassStudent,
    AcademicClassSyncJob,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.academic import daily_academic_pipeline as runtime
from app.services.academic.sync_enrollment import AcademicSyncEnrollmentWorkflowService


class FakeCelery:
    def __init__(self):
        self.sent = []

    def send_task(self, name, args=None, **options):
        self.sent.append((name, list(args or []), options))
        return SimpleNamespace(id=f"task-{len(self.sent)}")


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (
        AcademicTerm,
        AcademicClass,
        AcademicBulkOperationJob,
        AcademicClassSyncJob,
    ):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _scope(branch: str, class_count: int) -> dict[str, object]:
    class_ids = [f"class-{branch}-{index}" for index in range(class_count)]
    campus = "hn" if branch == "poly" else "hcm"
    return {
        "policy_version": runtime.DAILY_POLICY_VERSION,
        "scope_key": f"{branch}:term-{branch}",
        "scope_hash": f"hash-{branch}",
        "term_id": f"term-{branch}",
        "term_name": "Fall 2026",
        "branch": branch,
        "campuses": [campus],
        "class_ids": class_ids,
        "class_to_campus": {class_id: campus for class_id in class_ids},
    }


def _round_robin(scopes):
    rows = [list(scope["class_ids"]) for scope in scopes]
    return [
        class_id
        for index in range(max((len(row) for row in rows), default=0))
        for row in rows
        for class_id in row[index:index + 1]
    ]


def _seed_stage_root(session_factory, *, phase: str, poly: int, ptcd: int):
    scopes = [_scope("poly", poly), _scope("ptcd", ptcd)]
    with session_factory() as db:
        root = AcademicBulkOperationJob(
            id="root-1",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            request_json={"run_date_vn": "2026-09-24", "scopes": scopes},
            result_json={
                "phase": phase,
                "stage_round": 0,
                "stage_target_keys": _round_robin(scopes),
                "attempts_by_stage": {},
                "frozen_scopes_after_ap": {
                    scope["scope_key"]: scope for scope in scopes
                },
                "artifacts": {},
            },
        )
        db.add(root)
        db.commit()
        runtime.ensure_scope_parents(db, root, scopes)
        root_id = str(root.id)
    return root_id


def test_provisioning_across_two_branches_has_only_four_active_children(
    monkeypatch,
    session_factory,
):
    root_id = _seed_stage_root(
        session_factory,
        phase="account_enrollment",
        poly=5,
        ptcd=5,
    )
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        active = db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.status.in_(["queued", "running"]),
        ).all()
        parent_ids = {job.parent_job_id for job in active}
        branches = {
            db.get(AcademicBulkOperationJob, parent_id).branch
            for parent_id in parent_ids
        }
        assert len(active) == 4
        assert branches == {"poly", "ptcd"}
        assert {job.job_type for job in active} == {"full_cms_sync"}
        assert all(job.request_json["auto_map_course"] is False for job in active)
        assert all(job.request_json["sync_learning"] is False for job in active)
        assert all(job.force is True for job in active)
        assert all(job.request_json["force"] is True for job in active)
        assert all(job.request_json["request_contract"]["force"] is True for job in active)


@pytest.mark.parametrize('phase', ['account_enrollment', 'score_update'])
def test_ten_slot_trial_is_shared_across_branches_and_keeps_child_ids(
    monkeypatch, session_factory, phase,
):
    root_id = _seed_stage_root(session_factory, phase=phase, poly=8, ptcd=8)
    monkeypatch.setattr(runtime, 'SessionLocal', session_factory)
    monkeypatch.setattr(runtime.settings, 'academic_bulk_sync_dispatch_window', 10)
    celery = FakeCelery()
    runtime.run_daily_academic_pipeline(celery, root_id)
    with session_factory() as db:
        jobs = db.query(AcademicClassSyncJob).all()
        original_ids = {job.id for job in jobs}
        assert len(jobs) == 10
        assert {db.get(AcademicBulkOperationJob, job.parent_job_id).branch for job in jobs} == {'poly', 'ptcd'}
        assert all(job.status == 'queued' for job in jobs)
        assert all(sent[2]['queue'] == 'sync-bulk' for sent in celery.sent
                   if sent[0] == 'academic_class_sync_task')
    runtime.run_daily_academic_pipeline(celery, root_id)
    with session_factory() as db:
        assert {job.id for job in db.query(AcademicClassSyncJob).all()} == original_ids
    assert len([sent for sent in celery.sent if sent[0] == 'academic_class_sync_task']) == 10
    # A rollback to four must not cancel ten already submitted children.
    monkeypatch.setattr(runtime.settings, 'academic_bulk_sync_dispatch_window', 4)
    runtime.run_daily_academic_pipeline(celery, root_id)
    with session_factory() as db:
        assert {job.id for job in db.query(AcademicClassSyncJob).all()} == original_ids
        assert all(job.status == 'queued' for job in db.query(AcademicClassSyncJob).all())
    assert len([sent for sent in celery.sent if sent[0] == 'academic_class_sync_task']) == 10
    # Re-enable ten: only freed slots are filled, and completed work is kept.
    monkeypatch.setattr(runtime.settings, 'academic_bulk_sync_dispatch_window', 10)
    with session_factory() as db:
        for job in db.query(AcademicClassSyncJob).order_by(AcademicClassSyncJob.id).limit(3).all():
            job.status = 'completed'
        db.commit()
    runtime.run_daily_academic_pipeline(celery, root_id)
    with session_factory() as db:
        assert db.query(AcademicClassSyncJob).count() == 13
        assert db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.status == 'queued').count() == 10
        assert db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.status == 'completed').count() == 3
    assert len([sent for sent in celery.sent if sent[0] == 'academic_class_sync_task']) == 13


def test_score_stage_does_not_start_until_all_provisioning_retries_succeed(
    monkeypatch,
    session_factory,
):
    root_id = _seed_stage_root(
        session_factory,
        phase="account_enrollment",
        poly=1,
        ptcd=1,
    )
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        scopes = root.result_json["frozen_scopes_after_ap"]
        parents = runtime.ensure_scope_parents(db, root, list(scopes.values()))
        jobs = {}
        for branch, status in (("poly", "completed"), ("ptcd", "failed")):
            class_id = f"class-{branch}-0"
            parent = parents[f"{branch}:term-{branch}:provision"]
            job = AcademicClassSyncJob(
                id=f"provision-{branch}-2",
                job_type="full_cms_sync",
                status=status,
                class_id=class_id,
                parent_job_id=parent.id,
                idempotency_key=f"attempt:{branch}:2",
                request_json={"attempt_no": 2, "stage_managed_retries": True},
                result_json={},
            )
            db.add(job)
            jobs[class_id] = job.id
        state = dict(root.result_json)
        state["stage_round"] = 2
        state["attempts_by_stage"] = {"account_enrollment": {"2": jobs}}
        root.result_json = state
        db.add(root)
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        jobs = db.query(AcademicClassSyncJob).all()
        assert not [job for job in jobs if job.job_type == "learning_sync"]
        root = db.get(AcademicBulkOperationJob, root_id)
        assert root.result_json["stage_round"] == 3
        retry_ids = root.result_json["attempts_by_stage"]["account_enrollment"]["3"]
        assert list(retry_ids) == ["class-ptcd-0"]


def test_foreign_manual_class_job_blocks_but_is_never_adopted(
    monkeypatch,
    session_factory,
):
    root_id = _seed_stage_root(
        session_factory,
        phase="account_enrollment",
        poly=1,
        ptcd=1,
    )
    with session_factory() as db:
        db.add(AcademicClassSyncJob(
            id="manual-poly",
            job_type="full_cms_sync",
            status="running",
            class_id="class-poly-0",
            parent_job_id=None,
            idempotency_key="manual:poly",
            request_json={"scheduled": False},
            result_json={},
        ))
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        manual = db.get(AcademicClassSyncJob, "manual-poly")
        scheduled_poly = db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.class_id == "class-poly-0",
            AcademicClassSyncJob.id != manual.id,
        ).all()
        active = db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.status.in_(["queued", "running"]),
        ).count()
        assert manual.parent_job_id is None
        assert scheduled_poly == []
        assert active <= 4


def test_provisioning_gap_only_lists_missing_account_and_enrollment_effects():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AcademicClass,
        AcademicStudent,
        AcademicClassStudent,
        OpenEdXUserMapping,
        AcademicStudentLearningSnapshot,
    ):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(AcademicClass(
            id="class-1",
            term_id="term-1",
            subject_id="subject-1",
            class_code="DOM101.01",
            campus="hn",
            branch="poly",
            active=True,
        ))
        db.add_all([
            AcademicStudent(
                id="student-1",
                student_code="PH00001",
                username="ap-one",
                full_name="One",
            ),
            AcademicStudent(
                id="student-2",
                student_code="PH00002",
                username="ap-two",
                full_name="Two",
            ),
            AcademicClassStudent(
                id="roster-1",
                class_id="class-1",
                student_id="student-1",
            ),
            AcademicClassStudent(
                id="roster-2",
                class_id="class-1",
                student_id="student-2",
            ),
            OpenEdXUserMapping(
                id="mapping-1",
                student_id="student-1",
                ap_username="ap-one",
                openedx_username="PH00001",
                openedx_is_active=True,
                match_status="matched",
            ),
            AcademicStudentLearningSnapshot(
                id="snapshot-1",
                class_id="class-1",
                student_id="student-1",
                openedx_course_id="course-v1:FPL+DOM101+FA26",
                enrollment_status="enrolled",
            ),
        ])
        db.commit()
        parent = SimpleNamespace(
            rbac=None,
            effective_course_mapping_for_class=lambda cls: SimpleNamespace(
                openedx_course_id="course-v1:FPL+DOM101+FA26",
            ),
        )

        result = AcademicSyncEnrollmentWorkflowService(
            db,
            parent,
        ).class_provisioning_gap("class-1")

        assert result["reconciled_student_ids"] == ["student-1", "student-2"]
        assert result["missing_account_student_ids"] == ["student-2"]
        assert result["missing_enrollment_student_ids"] == ["student-2"]
    engine.dispose()

def test_score_completion_publishes_snapshot_continuation_and_updates_scope_state(
    monkeypatch,
    session_factory,
):
    root_id = _seed_stage_root(
        session_factory,
        phase="score_update",
        poly=1,
        ptcd=1,
    )
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        scopes = list(root.result_json["frozen_scopes_after_ap"].values())
        parents = runtime.ensure_scope_parents(db, root, scopes)
        attempts = {}
        for branch in ("poly", "ptcd"):
            class_id = f"class-{branch}-0"
            parent = parents[f"{branch}:term-{branch}:score-report"]
            job = AcademicClassSyncJob(
                id=f"score-{branch}",
                job_type="learning_sync",
                status="completed",
                class_id=class_id,
                parent_job_id=parent.id,
                idempotency_key=f"score:{branch}",
                request_json={
                    "daily_root_job_id": root.id,
                    "attempt_no": 0,
                    "stage_managed_retries": True,
                },
                result_json={},
            )
            db.add(job)
            attempts[class_id] = job.id
        state = dict(root.result_json)
        state["attempts_by_stage"] = {"score_update": {"0": attempts}}
        root.result_json = state
        db.add(root)
        db.commit()

    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    celery = FakeCelery()
    result = runtime.run_daily_academic_pipeline(celery, root_id)

    assert result["status"] == "stage_complete"
    assert result["phase"] == "campus_snapshots"
    assert celery.sent[-1][0] == runtime.DAILY_ROOT_TASK
    assert celery.sent[-1][1] == [root_id]

    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        assert root.result_json["phase"] == "campus_snapshots"
        assert root.progress_current == 75
        provision = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.parent_job_id == root.id,
            AcademicBulkOperationJob.job_type == "academic_daily_provision_scope",
        ).all()
        score_report = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.parent_job_id == root.id,
            AcademicBulkOperationJob.job_type == "academic_daily_score-report_scope",
        ).all()
        assert {item.status for item in provision} == {"completed"}
        assert {item.status for item in score_report} == {"running"}


def test_class_stage_failure_keeps_child_error_message(session_factory):
    with session_factory() as db:
        root = AcademicBulkOperationJob(
            id="root-class-failure",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            request_json={},
            result_json={},
        )
        attempt = AcademicClassSyncJob(
            id="class-failed",
            job_type="learning_sync",
            status="failed",
            class_id="class-poly-0",
            idempotency_key="class-failed-key",
            error_message="statement timeout while refreshing grade snapshot",
            request_json={},
            result_json={},
        )
        db.add_all([root, attempt])
        db.commit()

        runtime._fail_exhausted_stage(
            db,
            root,
            {},
            stage="score_update",
            failed_target_keys=("class-poly-0",),
            attempt_ids={"class-poly-0": attempt.id},
        )
        db.refresh(root)

    assert "statement timeout while refreshing grade snapshot" in root.error_message

def test_daily_provisioning_and_score_stages_force_full_roster_refresh():
    root = SimpleNamespace(
        id="root-score-force",
        request_json={"run_date_vn": "2026-10-04"},
    )
    parent = SimpleNamespace(id="score-parent")
    scope = {
        "scope_key": "poly:term-poly",
        "scope_hash": "scope-hash",
    }

    provision = runtime._class_attempt_request(
        root,
        parent,
        scope,
        "class-1",
        stage="account_enrollment",
        round_no=0,
    )
    score = runtime._class_attempt_request(
        root,
        parent,
        scope,
        "class-1",
        stage="score_update",
        round_no=0,
    )

    assert provision["force"] is True
    assert provision["sync_learning"] is False
    assert score["force"] is True
    assert score["sync_learning"] is True
