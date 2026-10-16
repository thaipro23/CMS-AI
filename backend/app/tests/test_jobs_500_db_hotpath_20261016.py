"""Regressions for /jobs 500 from database timeouts, October 16 2026."""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicClassSyncJob
from app.models.learning_analytics import AnalyticsTrackingEvent
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def test_tracking_gate_is_exact_and_count_contract_is_explicit_on_sqlite():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AnalyticsTrackingEvent.__table__.create(engine)
    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)
        assert service._tracking_event_volume(minimum=1) == (0, False, False)
        for i in range(3):
            db.add(AnalyticsTrackingEvent(raw_line_hash=f'event-{i}', event_type='play_video'))
        db.commit()
        assert service._tracking_event_volume(minimum=1) == (3, False, True)
        assert service._tracking_event_volume(minimum=4) == (3, False, False)
    engine.dispose()


def test_ops_reuses_report_components_without_counting_event_table(monkeypatch):
    class Query:
        def order_by(self, *args):
            return self
        def first(self):
            return None
    service = LearningAnalyticsCoreService(SimpleNamespace(query=lambda *_: Query()))
    calls = []
    monkeypatch.setattr(service, 'ingest_status', lambda: {'last_status': 'completed'})
    monkeypatch.setattr(service, 'analytics_data_quality_report', lambda: {'readiness': 'READY', 'issues': []})
    monkeypatch.setattr(service, 'rollout_control_report', lambda **kwargs: {'rollout_status': 'READY', 'mode': 'PRODUCTION', 'counters': {'in_rollout': 3}})
    monkeypatch.setattr(service, 'analytics_monitoring_report', lambda: {'monitoring_status': 'OK', 'stuck_analytics_job_count': 0, 'stale_snapshot_count': 0})

    def readiness(*, _shared=None):
        calls.append(_shared)
        return {'checks': {
            'active_recalculate_jobs': 0,
            'tracking_event_count': 14447732,
            'tracking_event_count_is_estimate': True,
            'tracking_event_minimum_met': True,
            'behavior_snapshot_count': 3,
        }, 'readiness': 'PRODUCTION_READY',
            'ready_for_production': True, 'blocker_count': 0, 'warning_count': 0}

    monkeypatch.setattr(service, 'production_readiness_report', readiness)
    result = service.ops_status()
    assert len(calls) == 1
    assert set(calls[0]) == {'data_quality', 'rollout', 'monitoring'}
    assert result['tracking_event_count_is_estimate'] is True
    assert result['tracking_event_minimum_met'] is True
    assert result['rollout_in_scope_classes'] == 3


def test_class_job_composite_index_and_query_scope_contract():
    indexes = {index.name for index in AcademicClassSyncJob.__table__.indexes}
    assert 'ix_academic_class_sync_jobs_status_created' in indexes

    from app.api.routes import academic
    import inspect as python_inspect
    body = python_inspect.getsource(academic.list_recent_class_sync_jobs)
    assert 'service.visible_class_ids' in body
    assert 'service.assert_can_access_class(user, class_id)' in body
    assert 'reconcile_class_sync_jobs(db)' in body
