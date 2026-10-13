from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.academic import AcademicClass, AcademicClassSyncJob
from app.models.learning_analytics import (
    AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentSessionProgress, AnalyticsStudentVideoProgress, AnalyticsTrackingEvent,
)
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


@pytest.mark.parametrize('roster_name,expected_count', [('student', 2), ('missing-student', 0)])
def test_doctor_tracking_stats_use_one_aggregate_and_preserve_roster_scope(monkeypatch, roster_name, expected_count):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (AnalyticsLearningBehaviorSnapshot, AnalyticsTrackingEvent,
                  AnalyticsStudentVideoProgress, AnalyticsStudentSessionProgress,
                  AnalyticsCourseSession, AcademicClassSyncJob):
        model.__table__.create(engine)
    cls = SimpleNamespace(subject_id=None, term_id=None, class_code='BUS1052',
                          class_name='Class', campus='DN', branch='poly')
    with Session(engine) as session:
        class Database:
            def get(self, model, key):
                return cls if model is AcademicClass else session.get(model, key)

            def __getattr__(self, name):
                return getattr(session, name)

        for index, (course, username, date) in enumerate([
            ('course', 'student', datetime(2026, 10, 1)),
            ('course', 'student', datetime(2026, 10, 2)),
            ('course', 'outsider', datetime(2026, 10, 3)),
            ('other-course', 'student', datetime(2026, 10, 4)),
        ]):
            session.add(AnalyticsTrackingEvent(raw_line_hash=f'event-{index}',
                course_id=course, username=username, event_time=date, event_type='page_view'))
        session.commit()
        service = LearningAnalyticsCoreService(Database())
        monkeypatch.setattr(service, '_class_student_roster', lambda *args: [{'username': roster_name}])
        monkeypatch.setattr(service, '_class_course_mapping_diagnostics', lambda **kwargs:
                            {'resolved_course_id': 'course', 'status': 'mapped'})
        monkeypatch.setattr(service, 'analytics_enqueue_guard', lambda **kwargs: {'allowed': True})
        queries = []
        def observe(conn, cursor, statement, params, context, many):
            if 'analytics_tracking_events' in statement:
                queries.append(statement)
        event.listen(engine, 'before_cursor_execute', observe)
        result = service.class_result_doctor(class_id='class', course_id='course')
        event.remove(engine, 'before_cursor_execute', observe)
        assert result['tracking_event_count'] == expected_count
        assert result['tracking_user_count'] == (1 if expected_count else 0)
        if expected_count:
            assert result['latest_tracking_event_at'].startswith('2026-10-02')
        else:
            assert result['latest_tracking_event_at'] is None
        assert len(queries) == 1
        assert 'count(' in queries[0].lower() and 'max(' in queries[0].lower()
    engine.dispose()


def test_workspace_reuses_one_doctor_for_summary_rows_and_response(monkeypatch):
    from app.api.routes import learning_analytics as route

    class Query:
        def filter(self, *args): return self
        def order_by(self, *args): return self
        def all(self): return []

    service = LearningAnalyticsCoreService(SimpleNamespace(query=lambda *args: Query()))
    workflow = service._analytics_results_workflow()
    monkeypatch.setattr(service, '_analytics_results_workflow', lambda: workflow)
    monkeypatch.setattr(service, '_class_student_roster', lambda *args: [])
    monkeypatch.setattr(service, '_course_for_class', lambda *args: 'course')
    calls = []
    doctor = {'status': 'ready', 'tracking_event_count': 2}
    def read_doctor(**kwargs):
        calls.append(kwargs)
        return doctor
    monkeypatch.setattr(workflow, 'class_result_doctor', read_doctor)
    access = []
    monkeypatch.setattr(route, '_assert_analytics_class_access', lambda *args: access.append(args))
    monkeypatch.setattr(route, '_analytics_permission_scope', lambda *args: {'allowed': True})
    monkeypatch.setattr(route, 'LearningAnalyticsCoreService', lambda db: service)
    result = route.class_behavior_workspace('class', course_id='course', classification=None,
                                            limit=200, offset=0, db=service.db, user=object())
    assert len(access) == 1
    assert len(calls) == 1
    assert result['doctor'] == result['summary']['diagnostics'] == result['rows']['diagnostics'] == doctor
    assert result['read_only'] is True
