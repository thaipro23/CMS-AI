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
               page_url=unit, event_source='server', raw_event={'unit_usage_key': unit}))
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
