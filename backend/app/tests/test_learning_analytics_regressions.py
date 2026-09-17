from __future__ import annotations

import re

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, Session

from app.models.academic import AcademicClass
from app.models.learning_analytics import AnalyticsLearningBehaviorSnapshot
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def _engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClass.__table__.create(engine)
    AnalyticsLearningBehaviorSnapshot.__table__.create(engine)
    return engine


def test_mapping_diagnostics_and_rollout_helpers_are_real_instance_methods():
    engine = _engine()
    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)

        diagnostics = service._class_course_mapping_diagnostics(class_id='missing-class')
        in_rollout, reasons = service._class_matches_rollout(None)

        assert diagnostics['status'] == 'missing_class'
        assert isinstance(in_rollout, bool)
        assert isinstance(reasons, list)
    engine.dispose()


def test_learning_dashboard_never_loads_the_full_snapshot_scope_before_aggregation(monkeypatch):
    engine = _engine()
    with Session(engine) as db:
        classroom = AcademicClass(
            id='class-1',
            term_id='term-1',
            subject_id='subject-1',
            class_code='SOA102.01',
            class_name='SOA102.01',
            campus='hn',
            branch='poly',
            active=True,
        )
        db.add(classroom)
        labels = [
            ('LIKELY_REAL_LEARNING', 0, 0, 95),
            ('POSSIBLE_IDLE', 80, 0, 70),
            ('POSSIBLE_ANOMALY', 0, 90, 65),
            ('NORMAL', 0, 0, 85),
            ('INSUFFICIENT_DATA', 0, 0, None),
        ]
        for index, (classification, idle, suspicious, deadline) in enumerate(labels, 1):
            db.add(AnalyticsLearningBehaviorSnapshot(
                id=f'snapshot-{index}',
                class_id=classroom.id,
                course_id='course-v1:FPL+SOA102+FA26',
                username=f'student-{index}',
                classification=classification,
                display_label=classification,
                idle_score=idle,
                suspicious_score=suspicious,
                confidence_score=50 + index,
                deadline_compliance_percent=deadline,
                crammed_session_count=1 if index == 3 else 0,
                data_quality='GOOD' if index < 5 else 'MISSING',
            ))
        db.commit()

        original_all = Query.all

        def guarded_all(query):
            sql = re.sub(r'\s+', ' ', str(query.statement)).upper()
            if (
                'ANALYTICS_LEARNING_BEHAVIOR_SNAPSHOTS' in sql
                and ' GROUP BY ' not in sql
                and ' LIMIT ' not in sql
            ):
                raise AssertionError('dashboard attempted an unbounded full snapshot load')
            return original_all(query)

        monkeypatch.setattr(Query, 'all', guarded_all)
        result = LearningAnalyticsCoreService(db).learning_dashboard(limit=2)

        assert result['total_students'] == 5
        assert result['possible_idle_count'] == 1
        assert result['possible_suspicious_count'] == 1
        assert len(result['top_possible_suspicious']) <= 2
        assert len(result['top_possible_idle']) <= 2
        assert len(result['deadline_attention']) <= 2
    engine.dispose()
