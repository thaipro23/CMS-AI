from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicTeacherReportJob
from app.services.academic.daily_teacher_report_runtime import (
    JOB_RUNTIME_EXCEEDED,
    reconcile_teacher_report_watchdog,
)


NOW = datetime(2026, 9, 14, 14, 10, 0)


def _engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicTeacherReportJob.__table__.create(engine)
    return engine


def test_seven_hour_ghost_job_is_failed_even_when_updated_at_is_recent():
    engine = _engine()
    with Session(engine) as db:
        job = AcademicTeacherReportJob(
            id='2ea2792f-c747-48a1-ba7c-eae13bc93933',
            job_type='rebuild_cache',
            status='running',
            term_id=None,
            branch='poly',
            campus=None,
            requested_by='12213',
            progress_current=50,
            progress_total=100,
            progress_label='Đang lấy điểm CMS mới nhất: WD22301',
            request_json={
                'learning_platform': 'cms',
                'teacher_id': None,
                'class_id': None,
            },
            result_json={},
            created_at=NOW - timedelta(hours=7),
            started_at=NOW - timedelta(hours=7),
            # This models production exactly: some code touched updated_at even
            # though Celery had no ACTIVE/RESERVED/SCHEDULED task anymore.
            updated_at=NOW - timedelta(seconds=5),
        )
        db.add(job)
        db.commit()

        result = reconcile_teacher_report_watchdog(db, now=NOW)
        db.refresh(job)

        assert result['teacher_failed'] == 1
        assert job.status == 'failed'
        assert job.result_json['code'] == JOB_RUNTIME_EXCEEDED
        assert job.progress_current == 50
        assert job.finished_at == NOW

    engine.dispose()


def test_recent_local_management_job_is_not_failed():
    engine = _engine()
    with Session(engine) as db:
        job = AcademicTeacherReportJob(
            id='healthy-management-job',
            job_type='rebuild_cache',
            status='running',
            progress_current=40,
            progress_total=100,
            progress_label='Đang tính cache local',
            request_json={'teacher_id': None, 'class_id': None},
            result_json={
                '_runtime': {
                    'heartbeat_at': '2026-09-14T21:09:30+07:00',
                    'progress_changed_at': '2026-09-14T21:09:00+07:00',
                    'phase': 'building_cache',
                }
            },
            created_at=NOW - timedelta(minutes=2),
            started_at=NOW - timedelta(minutes=2),
            updated_at=NOW,
        )
        db.add(job)
        db.commit()

        result = reconcile_teacher_report_watchdog(db, now=NOW)
        db.refresh(job)

        assert result['teacher_failed'] == 0
        assert job.status == 'running'

    engine.dispose()
