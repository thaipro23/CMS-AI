from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.learning_analytics import (
    AnalyticsQuizAttempt, AnalyticsQuizItemSubmission, AnalyticsQuizItemReceipt,
    AnalyticsQuizIntegrityResult, AnalyticsMaterializedEventReceipt, AnalyticsTrackingEvent,
)
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def test_late_start_and_duplicate_delivery_keep_one_attempt_and_durable_answer():
    engine = create_engine('sqlite://')
    for model in (AnalyticsTrackingEvent, AnalyticsMaterializedEventReceipt, AnalyticsQuizAttempt,
                  AnalyticsQuizItemSubmission, AnalyticsQuizItemReceipt, AnalyticsQuizIntegrityResult):
        model.__table__.create(engine)
    start = datetime(2026, 10, 5)
    unit = 'block-v1:FPS+COM1091+FA26+type@vertical+block@u'
    payload = {'problem_id': 'q1', 'grade': 1, 'max_grade': 1,
               'submission': {'input1': {'answer': 'A', 'correct': True,
                                         'variant': '', 'response_type': 'multiplechoiceresponse'}}}
    # Match production SessionLocal; default autoflush would hide duplicate inserts.
    with Session(engine, autoflush=False) as db:
        for i in range(2):
            db.add(AnalyticsTrackingEvent(id=f'e{i}', raw_line_hash=f'h{i}',
                   username='sv', user_id='1', course_id='course', event_source='openedx_tracking_loki',
                   event_type='problem_check', event_time=start + timedelta(seconds=205),
                   page_url=unit + '?format=Quiz', raw_event=payload, raw_json={'event_source': 'server'}))
        db.commit()
        service = LearningAnalyticsCoreService(db)
        service.recalculate_course_quiz_attempts(course_id='course', username='sv')
        assert db.query(AnalyticsQuizItemSubmission).count() == 1
        assert db.query(AnalyticsQuizItemReceipt).count() == 2
        assert db.query(AnalyticsQuizAttempt).one().submission_count == 1
        db.add(AnalyticsTrackingEvent(id='s1', raw_line_hash='start', username='sv', user_id='1',
               course_id='course', event_type='/api/unit-reset/v1/quiz-session/start', event_time=start,
               page_url=unit, event_source='server', raw_event={'unit_usage_key': unit,
                   'unit_reset_nonce': 'quiz-session:1', 'started_at': start.isoformat()}))
        db.commit()
        service.recalculate_course_quiz_attempts(course_id='course', username='sv')
        attempts = db.query(AnalyticsQuizAttempt).all()
        assert len(attempts) == 1
        assert attempts[0].evidence_json['duration_seconds'] == 205
        assert (attempts[0].score_earned, attempts[0].score_possible) == (1, 1)
        # Delete staging records, then a recalculation must retain item history.
        db.query(AnalyticsTrackingEvent).delete(synchronize_session=False)
        # Legacy heuristic flags must not survive merely because raw logs expired.
        attempts[0].suspicious_quiz_speed = True
        attempts[0].fishing_pattern = True
        db.commit()
        service.recalculate_course_quiz_attempts(course_id='course', username='sv')
        assert db.query(AnalyticsQuizItemSubmission).one().answer_json == 'A'
        assert db.query(AnalyticsQuizAttempt).one().evidence_json['duration_seconds'] == 205
        assert db.query(AnalyticsQuizAttempt).one().suspicious_quiz_speed is False
        assert db.query(AnalyticsQuizAttempt).one().fishing_pattern is False
        # A reveal request arriving late still applies after the original checks expire.
        db.add(AnalyticsTrackingEvent(id='reveal1', raw_line_hash='reveal', username='sv', user_id='1',
               course_id='course', event_type='showanswer', event_time=start + timedelta(seconds=100),
               page_url=unit, event_source='server', raw_event={'problem_id': 'q1'}))
        db.commit()
        service.recalculate_course_quiz_attempts(course_id='course', username='sv')
        assert db.query(AnalyticsQuizItemSubmission).one().reveal_requested_before is True
        # Retained evidence from old URL requests is not a successful session.
        row = db.get(AnalyticsQuizAttempt, attempts[0].id)
        row.reset_count = 3
        row.evidence_json = {**row.evidence_json, 'session_event_provenance': None,
                            'reset_times': [start.isoformat()]}
        db.commit()
        service.recalculate_course_quiz_attempts(course_id='course', username='sv')
        assert row.reset_count == 0
        assert row.evidence_json['duration_seconds'] is None
        assert row.evidence_json['reset_times'] == []
        assert (row.score_earned, row.score_possible) == (1, 1)


def test_student_scope_rejects_wrong_class_and_wrong_course(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.api.routes import learning_analytics
    class Service:
        def __init__(self, db):
            pass
        def _class_student_usernames(self, class_id):
            return {'poly'} if class_id == 'poly-class' else {'ptcd'}
        def _course_for_class(self, class_id):
            return 'poly-course' if class_id == 'poly-class' else 'ptcd-course'
    monkeypatch.setattr(learning_analytics, 'LearningAnalyticsCoreService', Service)
    assert learning_analytics._assert_student_detail_scope(None, 'poly-class', 'poly', None) == 'poly-course'
    with pytest.raises(HTTPException) as exc:
        learning_analytics._assert_student_detail_scope(None, 'poly-class', 'ptcd', None)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        learning_analytics._assert_student_detail_scope(None, 'poly-class', 'poly', 'ptcd-course')
    assert exc.value.status_code == 403


def test_course_structure_groups_server_problem_checks_into_their_quiz_unit():
    from app.models.learning_analytics import AnalyticsCourseSession
    engine = create_engine('sqlite://')
    for model in (AnalyticsTrackingEvent, AnalyticsMaterializedEventReceipt, AnalyticsQuizAttempt,
                  AnalyticsQuizItemSubmission, AnalyticsQuizItemReceipt, AnalyticsQuizIntegrityResult,
                  AnalyticsCourseSession):
        model.__table__.create(engine)
    unit = 'block-v1:FPL+SUB+FA26+type@vertical+block@unit'
    with Session(engine, autoflush=False) as db:
        db.add(AnalyticsCourseSession(course_id='course', session_index=1, session_key='lesson',
            session_title='Bài 1', active=True, components_json={'components': [
                {'usage_key': key, 'block_type': 'problem', 'metadata': {'parent_block_id': unit}}
                for key in ('problem-a', 'problem-b')]}))
        for number, key in enumerate(('problem-a', 'problem-b')):
            db.add(AnalyticsTrackingEvent(id=key, raw_line_hash=key, course_id='course',
                username='sv', user_id='1', event_type='problem_check', event_source='server',
                event_time=datetime(2026, 10, 7) + timedelta(seconds=number * 40),
                raw_event={'problem_id': key, 'grade': 1, 'max_grade': 1}))
        db.commit()
        LearningAnalyticsCoreService(db).recalculate_course_quiz_attempts(course_id='course', username='sv')
        attempt = db.query(AnalyticsQuizAttempt).one()
        assert attempt.unit_usage_key == unit
        assert attempt.submission_count == 2
        assert (attempt.score_earned, attempt.score_possible) == (2, 2)
