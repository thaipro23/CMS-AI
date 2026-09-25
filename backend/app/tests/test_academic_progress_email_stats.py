from datetime import datetime, timedelta
import inspect

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicTeacherAssignment,
)


def test_class_filter_is_applied_in_sql_instead_of_scanning_all_mail_jobs():
    from app.services.academic.progress_email_stats import AcademicProgressEmailStatsService

    source = inspect.getsource(AcademicProgressEmailStatsService.for_classes)
    assert "request_json['class_id'].as_string().in_(requested_class_ids)" in source


def _db():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClass.__table__.create(engine)
    AcademicTeacherAssignment.__table__.create(engine)
    AcademicBulkOperationJob.__table__.create(engine)
    return engine, Session(engine)


def _job(
    job_id: str,
    *,
    class_id: str,
    branch: str = 'poly',
    campus: str = 'ph',
    term_id: str = 'term-1',
    sent_count: int = 0,
    confirmed: bool = True,
    deliveries: list[dict] | None = None,
    finished_at: datetime | None = None,
):
    return AcademicBulkOperationJob(
        id=job_id,
        job_type='progress_reminder_email',
        status='completed',
        term_id=term_id,
        branch=branch,
        campus=campus,
        request_json={'class_id': class_id},
        result_json={
            'mail_send_confirmed': confirmed,
            'sent_count': sent_count,
            'mail_send_deliveries': deliveries or [],
        },
        finished_at=finished_at,
    )


def test_confirmed_deliveries_are_counted_per_class_and_student_only():
    from app.services.academic.progress_email_stats import AcademicProgressEmailStatsService

    engine, db = _db()
    latest = datetime(2026, 9, 25, 2, 15)
    db.add_all([
        _job(
            'sent-1',
            class_id='class-1',
            sent_count=2,
            finished_at=latest,
            deliveries=[
                {'student_id': 'student-1', 'provider_state': 'terminal', 'status': 'COMPLETED', 'sent_count': 1, 'failed_count': 0},
                {'student_id': 'student-2', 'provider_state': 'terminal', 'status': 'FAILED', 'sent_count': 0, 'failed_count': 1},
                {'student_id': 'student-3', 'provider_state': 'provider_created', 'status': 'QUEUED', 'sent_count': 0, 'failed_count': 0},
            ],
        ),
        _job('unconfirmed', class_id='class-1', sent_count=9, confirmed=False),
    ])
    db.commit()

    stats = AcademicProgressEmailStatsService(db).for_classes({'class-1'})

    assert stats.class_sent_count == {'class-1': 2}
    assert stats.class_last_sent_at == {'class-1': latest}
    assert stats.student_sent_count == {('class-1', 'student-1'): 1}
    assert stats.student_last_sent_at == {('class-1', 'student-1'): latest}
    db.close()
    engine.dispose()


def test_legacy_aggregate_counts_for_class_without_fabricating_student_history():
    from app.services.academic.progress_email_stats import AcademicProgressEmailStatsService

    engine, db = _db()
    db.add(_job('legacy', class_id='class-1', sent_count=7, deliveries=[]))
    db.commit()

    stats = AcademicProgressEmailStatsService(db).for_classes({'class-1'})

    assert stats.class_sent_count['class-1'] == 7
    assert stats.student_sent_count == {}
    db.close()
    engine.dispose()


def test_teacher_totals_deduplicate_assignments_and_respect_scope_filters():
    from app.services.academic.progress_email_stats import AcademicProgressEmailStatsService

    engine, db = _db()
    db.add_all([
        AcademicClass(id='class-poly', term_id='term-1', subject_id='subject-1', class_code='POLY-1', branch='poly', campus='ph'),
        AcademicClass(id='class-ptcd', term_id='term-1', subject_id='subject-2', class_code='PTCD-1', branch='ptcd', campus='hn'),
        AcademicTeacherAssignment(id='a-1', teacher_id='teacher-1', class_id='class-poly', subject_id='subject-1', term_id='term-1', branch='poly', campus='ph'),
        AcademicTeacherAssignment(id='a-2', teacher_id='teacher-1', class_id='class-poly', subject_id='subject-1', term_id='term-1', block_id='block-2', branch='poly', campus='ph'),
        AcademicTeacherAssignment(id='a-3', teacher_id='teacher-1', class_id='class-ptcd', subject_id='subject-2', term_id='term-1', branch='ptcd', campus='hn'),
        _job('poly-job', class_id='class-poly', sent_count=3, branch='poly', campus='ph'),
        _job('ptcd-job', class_id='class-ptcd', sent_count=11, branch='ptcd', campus='hn'),
        _job('other-term', class_id='class-poly', sent_count=20, branch='poly', campus='ph', term_id='term-2'),
    ])
    db.commit()

    stats = AcademicProgressEmailStatsService(db).for_teachers(
        {'teacher-1'},
        term_id='term-1',
        branch='poly',
        campus='ph',
    )

    assert stats.teacher_sent_count == {'teacher-1': 3}
    assert stats.class_sent_count == {'class-poly': 3}
    assert 'class-ptcd' not in stats.class_sent_count
    db.close()
    engine.dispose()


def test_latest_confirmed_send_time_wins_across_multiple_jobs():
    from app.services.academic.progress_email_stats import AcademicProgressEmailStatsService

    engine, db = _db()
    older = datetime(2026, 9, 24, 1, 0)
    newer = older + timedelta(days=1)
    delivery = [{'student_id': 'student-1', 'provider_state': 'terminal', 'status': 'COMPLETED', 'sent_count': 1, 'failed_count': 0}]
    db.add_all([
        _job('older', class_id='class-1', sent_count=1, deliveries=delivery, finished_at=older),
        _job('newer', class_id='class-1', sent_count=1, deliveries=delivery, finished_at=newer),
    ])
    db.commit()

    stats = AcademicProgressEmailStatsService(db).for_classes({'class-1'})

    assert stats.class_sent_count['class-1'] == 2
    assert stats.student_sent_count[('class-1', 'student-1')] == 2
    assert stats.student_last_sent_at[('class-1', 'student-1')] == newer
    db.close()
    engine.dispose()
