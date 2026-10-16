"""Two real PostgreSQL transactions must preserve the newer ML cutoff."""
import os
import uuid
from datetime import datetime, timedelta
from threading import Event, Thread

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicCourseMapping, AcademicStudent, AcademicTerm, AcademicSubject, AcademicBlock
from app.models.learning_analytics import AnalyticsCourseSession, AnalyticsStudentVideoProgress, AnalyticsLearningBehaviorSnapshot
from app.services.learning_analytics.ml_workflow import LearningMLWorkflow

pytestmark = pytest.mark.integration


def test_overlapping_jobs_cannot_replace_a_newer_ml_result(monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Disposable PostgreSQL URL not configured')
    admin = create_engine(url)
    schema = 'ml_' + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    models = [AcademicTerm, AcademicSubject, AcademicBlock, AcademicClass, AcademicClassCourseMapping, AcademicCourseMapping, AcademicStudent,
        AcademicClassStudent, AnalyticsCourseSession, AnalyticsStudentVideoProgress, AnalyticsLearningBehaviorSnapshot]
    now = datetime.utcnow()
    monkeypatch.setattr(settings, 'analytics_ml_mode', 'shadow')
    monkeypatch.setattr(settings, 'analytics_ml_pilot_class_ids', 'class')
    started, finished = Event(), Event()
    errors, outcomes = [], []
    thread = None
    try:
        for model in models:
            model.__table__.create(engine)
        with Session(engine) as db:
            db.add(AcademicTerm(id='t', term_code='T', term_name='T'))
            db.add(AcademicSubject(id='s', subject_code='S', subject_name='S'))
            db.flush()
            db.add(AcademicClass(id='class', term_id='t', subject_id='s', class_code='C', active=True))
            db.flush()
            db.add(AcademicClassCourseMapping(class_id='class', openedx_course_id='course', active=True))
            db.add(AcademicStudent(id='s', username='u', student_code='U', active=True))
            db.flush()
            db.add(AcademicClassStudent(class_id='class', student_id='s'))
            db.add(AnalyticsLearningBehaviorSnapshot(id='snapshot', class_id='class', course_id='course',
                username='u', calculated_at=now, evidence_json={'rule':'kept'}))
            db.commit()
        import app.services.learning_analytics.ml_workflow as module
        original = module.score_cohorts
        def scoring(*args, **kwargs):
            result = original(*args, **kwargs)
            started.set()
            return result
        monkeypatch.setattr(module, 'score_cohorts', scoring)
        with Session(engine) as writer:
            row = writer.get(AnalyticsLearningBehaviorSnapshot, 'snapshot', with_for_update=True)
            row.evidence_json = {'rule':'new', 'ml': {'cutoff': (now+timedelta(seconds=1)).isoformat()}}
            writer.flush()
            def older_job():
                try:
                    with Session(engine) as reader:
                        reader.execute(text("SET LOCAL lock_timeout = '5s'"))
                        outcomes.append(LearningMLWorkflow(reader).score_behavior(class_id='class', course_id='course',
                            target_usernames=['u'], cutoff=now))
                        reader.commit()
                except Exception as exc:
                    errors.append(type(exc).__name__)
                finally:
                    finished.set()
            thread = Thread(target=older_job)
            thread.start()
            assert started.wait(5)
            assert not finished.wait(.1)  # Reader must wait for writer's row lock.
            writer.commit()
        thread.join(5)
        assert finished.is_set() and not errors
        assert len(outcomes)==1 and outcomes[0]['status']=='completed'
        assert outcomes[0]['processed']==0
        with Session(engine) as db:
            evidence = db.get(AnalyticsLearningBehaviorSnapshot, 'snapshot').evidence_json
            assert evidence['rule']=='new'
            assert evidence['ml']['cutoff']==(now+timedelta(seconds=1)).isoformat()
    finally:
        if thread:
            thread.join(6)
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
