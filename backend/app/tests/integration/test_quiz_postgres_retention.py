"""Run only against the explicitly provisioned, disposable CI database."""
import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.learning_analytics import (
    AnalyticsTrackingEvent, AnalyticsMaterializedEventReceipt, AnalyticsQuizAttempt,
    AnalyticsQuizItemSubmission, AnalyticsQuizItemReceipt,
)
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService

pytestmark = pytest.mark.integration


def test_postgres_cleanup_requires_item_receipt_and_keeps_durable_answers(monkeypatch):
    from app.core.config import settings
    database_url = os.environ.get('TEST_DATABASE_URL')
    if not database_url:
        pytest.skip('Disposable PostgreSQL TEST_DATABASE_URL is not configured')
    target = make_url(database_url)
    if target.database != 'ai_openedx_ci' or database_url != os.environ.get('DATABASE_URL'):
        pytest.fail('Refusing to mutate any database other than the configured disposable CI database')
    monkeypatch.setattr(settings, 'analytics_quiz_integrity_enabled', True)
    monkeypatch.setattr(settings, 'analytics_raw_event_retention_days', 3)
    engine = create_engine(database_url)
    token = str(uuid.uuid4())
    course = f'quiz-ci-{token}'
    safe_id, blocked_id = f'safe-{token}', f'blocked-{token}'
    with Session(engine, autoflush=False) as db:
        try:
            for event_id, username in ((safe_id, 'safe'), (blocked_id, 'blocked')):
                db.add(AnalyticsTrackingEvent(
                    id=event_id, raw_line_hash=event_id, course_id=course, username=username,
                    user_id='1', event_type='problem_check', event_source='server',
                    event_time=datetime.utcnow() - timedelta(days=4),
                    created_at=datetime.utcnow() - timedelta(days=4),
                    page_url='block-v1:CI+QUIZ+TEST+type@vertical+block@u',
                    raw_json={'event_source': 'server'},
                    raw_event={'problem_id': 'q1', 'grade': 1, 'max_grade': 1,
                               'content_version': 'v1', 'submission': {'input1': {
                                   'answer': 'A', 'correct': True, 'response_type': 'multiplechoiceresponse'}}},
                ))
            db.commit()
            # Old aggregate receipt alone must never authorize dropping answers.
            db.add(AnalyticsMaterializedEventReceipt(
                event_id=blocked_id, family='quiz', course_id=course, canonical_username='blocked'))
            db.commit()
            service = LearningAnalyticsCoreService(db)
            service.recalculate_course_quiz_attempts(course_id=course, username='safe')
            assert db.query(AnalyticsQuizItemReceipt).filter_by(event_id=safe_id).count() == 1
            service.cleanup_tracking_events()
            assert db.get(AnalyticsTrackingEvent, safe_id) is None
            assert db.get(AnalyticsTrackingEvent, blocked_id) is not None
            item = db.query(AnalyticsQuizItemSubmission).filter_by(course_id=course).one()
            assert item.answer_json == 'A'
            assert item.correct is True
        finally:
            db.rollback()
            for model in (AnalyticsQuizItemSubmission, AnalyticsQuizAttempt, AnalyticsTrackingEvent):
                db.query(model).filter_by(course_id=course).delete(synchronize_session=False)
            for model in (AnalyticsQuizItemReceipt, AnalyticsMaterializedEventReceipt):
                db.query(model).filter(model.event_id.in_([safe_id, blocked_id])).delete(synchronize_session=False)
            db.commit()
    engine.dispose()
