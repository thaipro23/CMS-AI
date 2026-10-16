"""Behavioral regression of scoped job visibility and bounded rollout aggregates."""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicClass, AcademicClassStudent, AcademicSubject, AcademicTeacherAssignment,
)
from app.models.learning_analytics import (
    AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
)
from app.services.academic.access import AcademicAccessWorkflowService
from app.services.academic.helpers import AccessDecision
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def test_visible_class_ids_matches_per_class_checks_for_teacher_and_campus(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for table in (AcademicSubject.__table__, AcademicClass.__table__, AcademicTeacherAssignment.__table__):
        table.create(engine)
    with Session(engine) as db:
        db.add(AcademicSubject(id='subject', subject_code='MEC101', subject_name='MEC', branch='poly'))
        rows = [
            AcademicClass(id='poly-hn', term_id='term', subject_id='subject', class_code='A', campus='HN', branch='poly'),
            AcademicClass(id='ptcd-hn', term_id='term', subject_id='subject', class_code='B', campus='HN', branch='ptcd'),
            AcademicClass(id='ptcd-assigned', term_id='term', subject_id='subject', class_code='C', campus='DN', branch='ptcd'),
        ]
        db.add_all(rows)
        db.add(AcademicTeacherAssignment(
            id='assignment', teacher_id='teacher', class_id='ptcd-assigned',
            subject_id='subject', term_id='term',
        ))
        db.commit()
        workflow = AcademicAccessWorkflowService(db, SimpleNamespace())
        decision = AccessDecision(
            unrestricted=False, teacher_ids={'teacher'}, subject_codes=set(),
            campus_codes={'hn'}, campus_branch_pairs={('poly', 'hn')},
        )
        monkeypatch.setattr(workflow, 'access_decision', lambda user: decision)
        user = SimpleNamespace()
        ids = {row.id for row in rows}
        visible = workflow.visible_class_ids(user, ids)
        assert visible == {'poly-hn', 'ptcd-assigned'}
        for class_id in visible:
            workflow.assert_can_access_class(user, class_id)
        from fastapi import HTTPException
        try:
            workflow.assert_can_access_class(user, 'ptcd-hn')
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError('PTCD class must not inherit Poly campus scope')
        assert workflow.visible_class_ids(user, set()) == set()
    engine.dispose()


def test_rollout_counts_are_batched_and_keep_per_class_result(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for table in (
        AcademicClass.__table__, AcademicClassStudent.__table__,
        AnalyticsCourseSession.__table__, AnalyticsLearningBehaviorSnapshot.__table__,
    ):
        table.create(engine)
    with Session(engine) as db:
        db.add_all([
            AcademicClass(id='c1', term_id='term', subject_id='subject', class_code='A', campus='HN', branch='poly'),
            AcademicClass(id='c2', term_id='term', subject_id='subject', class_code='B', campus='HN', branch='poly'),
        ])
        db.add(AcademicClassStudent(id='roster', class_id='c1', student_id='s1'))
        db.add(AnalyticsCourseSession(course_id='course', session_key='session-1', session_index=1))
        db.add(AnalyticsLearningBehaviorSnapshot(class_id='c1', course_id='course', username='s1'))
        db.commit()
        service = LearningAnalyticsCoreService(db)
        monkeypatch.setattr(service, '_course_for_class', lambda cls, preferred: 'course')
        monkeypatch.setattr(service, '_class_matches_rollout', lambda cls, mapped: (True, []))
        statements = []
        def on_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().lower().startswith('select'):
                statements.append(statement.lower())
        event.listen(engine, 'before_cursor_execute', on_execute)
        try:
            report = service.rollout_control_report(limit=2)
        finally:
            event.remove(engine, 'before_cursor_execute', on_execute)
        assert len(statements) <= 4, statements
        by_id = {row['class_id']: row for row in report['items']}
        assert by_id['c1']['student_count'] == 1
        assert by_id['c2']['student_count'] == 0
        assert by_id['c1']['behavior_snapshot_count'] == 1
        assert by_id['c2']['behavior_snapshot_count'] == 0
        assert by_id['c1']['session_count'] == 1
        assert by_id['c2']['session_count'] == 1
    engine.dispose()
