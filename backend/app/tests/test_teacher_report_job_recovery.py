from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.academic import reconcile_teacher_report_jobs
from app.models.academic import (
    AcademicClassStudent,
    AcademicStudentLearningSnapshot,
    AcademicTeacherReportJob,
)
from app.services.academic.teacher_report import AcademicTeacherReportWorkflowService


NOW = datetime(2026, 9, 12, 12, 0, 0)


def _engine_with(*models):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in models:
        model.__table__.create(engine)
    return engine


def test_refresh_contract_accepts_snapshot_age_for_replica_driven_platform():
    workflow = AcademicTeacherReportWorkflowService(None, SimpleNamespace())

    result = workflow.refresh_training_teacher_learning_data(
        SimpleNamespace(),
        term_id='term-1',
        learning_platform='udemy',
        max_snapshot_age_seconds=300,
    )

    assert result['ok'] is True
    assert result['snapshot_reused_class_count'] == 0


def test_complete_recent_class_snapshot_is_reused():
    engine = _engine_with(AcademicClassStudent, AcademicStudentLearningSnapshot)
    with Session(engine) as db:
        db.add(AcademicClassStudent(id='link-1', class_id='class-1', student_id='student-1'))
        db.add(AcademicStudentLearningSnapshot(
            id='snapshot-1',
            class_id='class-1',
            student_id='student-1',
            openedx_course_id='course-v1:FPL+MOB101+FA26',
            enrollment_status='enrolled',
            learning_synced_at=NOW - timedelta(seconds=30),
            last_synced_at=NOW - timedelta(seconds=30),
            raw_json={'grade_preserved': False},
        ))
        db.commit()
        workflow = AcademicTeacherReportWorkflowService(db, SimpleNamespace())

        assert workflow._teacher_report_class_snapshot_is_fresh(
            SimpleNamespace(id='class-1'),
            'course-v1:FPL+MOB101+FA26',
            max_age_seconds=300,
            now=NOW,
        ) is True
    engine.dispose()


def test_incomplete_or_preserved_class_snapshot_is_not_reused():
    engine = _engine_with(AcademicClassStudent, AcademicStudentLearningSnapshot)
    with Session(engine) as db:
        db.add_all([
            AcademicClassStudent(id='link-1', class_id='class-1', student_id='student-1'),
            AcademicClassStudent(id='link-2', class_id='class-1', student_id='student-2'),
            AcademicStudentLearningSnapshot(
                id='snapshot-1',
                class_id='class-1',
                student_id='student-1',
                openedx_course_id='course-v1:FPL+MOB101+FA26',
                enrollment_status='enrolled',
                learning_synced_at=NOW - timedelta(seconds=30),
                last_synced_at=NOW - timedelta(seconds=30),
                raw_json={'grade_preserved': True},
            ),
        ])
        db.commit()
        workflow = AcademicTeacherReportWorkflowService(db, SimpleNamespace())

        assert workflow._teacher_report_class_snapshot_is_fresh(
            SimpleNamespace(id='class-1'),
            'course-v1:FPL+MOB101+FA26',
            max_age_seconds=300,
            now=NOW,
        ) is False
    engine.dispose()


def test_old_running_export_is_failed_before_active_reuse():
    engine = _engine_with(AcademicTeacherReportJob)
    with Session(engine) as db:
        job = AcademicTeacherReportJob(
            id='report-1',
            job_type='export_excel',
            status='running',
            term_id='term-1',
            progress_current=55,
            progress_total=100,
            progress_label='Đang lấy điểm CMS mới nhất: MC21302',
            created_at=NOW - timedelta(hours=3),
            started_at=NOW - timedelta(hours=3),
            updated_at=NOW - timedelta(hours=3),
        )
        db.add(job)
        db.commit()

        changed = reconcile_teacher_report_jobs(db, now=NOW)
        db.refresh(job)

        assert changed == 1
        assert job.status == 'failed'
        assert job.result_json['code'] == 'CELERY_JOB_ORPHANED'
        assert job.progress_current == 55
    engine.dispose()

