from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicTeacherAssignment,
)


def _db():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClass.__table__.create(engine)
    AcademicTeacherAssignment.__table__.create(engine)
    AcademicBulkOperationJob.__table__.create(engine)
    return engine, Session(engine)


def _seed_scope(db: Session):
    sent_at = datetime(2026, 9, 25, 3, 30)
    db.add_all([
        AcademicClass(id='class-poly', term_id='term-1', subject_id='subject-1', class_code='POLY-1', branch='poly', campus='ph'),
        AcademicClass(id='class-ptcd', term_id='term-1', subject_id='subject-2', class_code='PTCD-1', branch='ptcd', campus='hn'),
        AcademicTeacherAssignment(id='assign-poly', teacher_id='teacher-1', class_id='class-poly', subject_id='subject-1', term_id='term-1', branch='poly', campus='ph'),
        AcademicTeacherAssignment(id='assign-ptcd', teacher_id='teacher-1', class_id='class-ptcd', subject_id='subject-2', term_id='term-1', branch='ptcd', campus='hn'),
        AcademicBulkOperationJob(
            id='mail-poly', job_type='progress_reminder_email', status='completed',
            term_id='term-1', branch='poly', campus='ph',
            request_json={'class_id': 'class-poly'},
            result_json={
                'mail_send_confirmed': True,
                'sent_count': 2,
                'mail_send_deliveries': [
                    {'student_id': 'student-1', 'provider_state': 'terminal', 'status': 'COMPLETED', 'sent_count': 1, 'failed_count': 0},
                ],
            },
            finished_at=sent_at,
        ),
        AcademicBulkOperationJob(
            id='mail-ptcd', job_type='progress_reminder_email', status='completed',
            term_id='term-1', branch='ptcd', campus='hn',
            request_json={'class_id': 'class-ptcd'},
            result_json={'mail_send_confirmed': True, 'sent_count': 9},
            finished_at=sent_at,
        ),
        AcademicBulkOperationJob(
            id='mail-contaminated-scope', job_type='progress_reminder_email', status='completed',
            term_id='term-1', branch='ptcd', campus='hn',
            request_json={'class_id': 'class-poly'},
            result_json={
                'mail_send_confirmed': True,
                'sent_count': 9,
                'mail_send_deliveries': [
                    {'student_id': 'student-1', 'provider_state': 'terminal', 'status': 'COMPLETED', 'sent_count': 9, 'failed_count': 0},
                ],
            },
            finished_at=sent_at,
        ),
    ])
    db.commit()
    return sent_at


def test_teacher_report_enrichment_adds_teacher_and_class_totals_with_scope():
    from app.api.routes.academic import _attach_progress_email_stats_to_teacher_report

    engine, db = _db()
    _seed_scope(db)
    report = {
        'items': [{
            'teacher_id': 'teacher-1',
            'classes': [
                {'class_id': 'class-poly'},
                {'class_id': 'class-ptcd'},
            ],
        }],
        'summary': {},
    }

    enriched = _attach_progress_email_stats_to_teacher_report(
        db,
        report,
        term_id='term-1',
        branch='poly',
        campus='ph',
        learning_platform='cms',
    )

    assert enriched['items'][0]['progress_email_sent_count'] == 2
    assert enriched['items'][0]['classes'][0]['progress_email_sent_count'] == 2
    assert enriched['items'][0]['classes'][1]['progress_email_sent_count'] == 0
    assert 'progress_email_sent_count' not in enriched['summary']
    db.close()
    engine.dispose()


def test_udemy_teacher_report_is_not_enriched_with_cms_mail_fields():
    from app.api.routes.academic import _attach_progress_email_stats_to_teacher_report

    engine, db = _db()
    report = {'items': [{'teacher_id': 'teacher-1'}], 'summary': {}}
    enriched = _attach_progress_email_stats_to_teacher_report(
        db, report, term_id='term-1', branch='poly', campus=None,
        learning_platform='udemy',
    )
    assert 'progress_email_sent_count' not in enriched['items'][0]
    db.close()
    engine.dispose()


def test_roster_enrichment_adds_confirmed_count_and_latest_time_to_visible_rows():
    from app.services.academic.roster import AcademicRosterWorkflowService

    engine, db = _db()
    sent_at = _seed_scope(db)
    service = AcademicRosterWorkflowService(db, parent=object())
    items = [
        {'id': 'student-1', 'full_name': 'One'},
        {'id': 'student-2', 'full_name': 'Two'},
    ]

    service._attach_progress_email_stats(
        'class-poly',
        items,
        term_id='term-1',
        branch='poly',
        campus='ph',
    )

    assert items[0]['progress_email_sent_count'] == 1
    assert items[0]['progress_email_last_sent_at'] == sent_at
    assert items[1]['progress_email_sent_count'] == 0
    assert items[1]['progress_email_last_sent_at'] is None
    db.close()
    engine.dispose()


def test_student_schema_keeps_mail_fields_in_response_projection():
    from app.schemas.academic import AcademicClassStudentOut

    fields = AcademicClassStudentOut.model_fields
    assert 'progress_email_sent_count' in fields
    assert 'progress_email_last_sent_at' in fields
