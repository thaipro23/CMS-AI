from types import SimpleNamespace

import pytest

from app.models.academic import AcademicClassStudent, AcademicStudentLearningSnapshot as Snapshot
from app.services.academic.component_read_cache import current_component_read_cache, snapshot_component_read_scope
from app.services.academic_service import AcademicService


def test_duplicate_component_identity_work_scales_linearly(monkeypatch):
    service = AcademicService(None)
    rows = [{'key': f'problem-{i}', 'name': f'Question {i}', 'earned': i % 10, 'possible': 10}
            for i in range(300)]
    calls = 0
    original = service._component_identity_key

    def identity(item):
        nonlocal calls
        calls += 1
        return original(item)

    monkeypatch.setattr(service, '_component_identity_key', identity)
    result = service._component_scores_from_payload({
        'component_scores': rows, 'component_grades': [dict(row) for row in rows],
        'grade': {'components': [dict(row) for row in rows]},
    })
    assert len(result) == 300
    assert {row['key']: row['earned'] for row in result} == {row['key']: row['earned'] for row in rows}
    assert calls <= 12 * len(rows)


def test_duplicate_planned_and_actual_zero_grades_keep_existing_preference():
    service = AcademicService(None)
    result = service._component_scores_from_payload({
        'component_scores': [{'name': 'Quiz 1', 'planned': True}],
        'component_grades': [{'name': 'Quiz 1', 'earned': 0, 'possible': 15},
                             {'name': 'Final test', 'earned': 60, 'possible': 60}],
        'grade': {'components': [{'name': 'Quiz 1', 'earned': 15, 'possible': 15}]},
    })
    assert len(result) == 2
    assert result[0]['earned'] == 0
    assert service._assessment_average_percent(result) == 50


def test_summary_normalizes_each_snapshot_once_and_rereads_on_next_call(monkeypatch):
    snapshots = [SimpleNamespace(
        student_id=f's{i}', raw_json={'payload': {'component_scores': [
            {'name': 'Quiz 1', 'earned': 10, 'possible': 10},
            {'name': 'Quiz 2', 'earned': 10, 'possible': 10},
        ]}}, enrollment_status='enrolled', progress_percent=0,
        grade_percent=100, completed_blocks=0, last_activity_at=None, passed=None,
        learning_synced_at=None, last_synced_at=None,
    ) for i in range(4)]

    class Query:
        def __init__(self, entities):
            self.entities = entities

        def filter(self, *args):
            return self

        def group_by(self, *args):
            return self

        def outerjoin(self, *args):
            return self

        def scalar(self):
            return len(snapshots) if getattr(self.entities[0], 'name', None) == 'count' else None

        def all(self):
            if self.entities[0] is Snapshot:
                return snapshots
            if self.entities[0] is Snapshot.enrollment_status:
                return [('enrolled', len(snapshots))]
            if self.entities[0] is AcademicClassStudent.student_id:
                return [(s.student_id, SimpleNamespace(match_status='matched')) for s in snapshots]
            raise AssertionError(self.entities)

    service = AcademicService(SimpleNamespace(
        query=lambda *entities: Query(entities), get=lambda *args: None,
    ))
    calls = 0
    original = service._component_scores_from_payload

    def normalize(payload):
        nonlocal calls
        calls += 1
        return original(payload)

    monkeypatch.setattr(service, '_component_scores_from_payload', normalize)
    first = service._learning_summary_for_class_course('class', 'course')
    assert first['avg_grade_percent'] == 100
    assert calls == len(snapshots)
    # Even an in-place edit between reads must be visible: no persistent cache.
    snapshots[0].raw_json['payload']['component_scores'][0]['earned'] = 0
    second = service._learning_summary_for_class_course('class', 'course')
    assert second['avg_grade_percent'] == 87.5
    assert calls == 2 * len(snapshots)


def test_read_cache_returns_independent_rows_and_observes_replaced_payload():
    service = AcademicService(None)
    snapshot = SimpleNamespace(raw_json={'payload': {'component_scores': [
        {'name': 'Quiz 1', 'earned': 8, 'possible': 10},
    ]}})

    @snapshot_component_read_scope
    def read():
        first = service._component_scores_from_snapshot(snapshot)
        first[0]['earned'] = 999
        assert service._component_scores_from_snapshot(snapshot)[0]['earned'] == 8
        snapshot.raw_json = {'payload': {'component_scores': [
            {'name': 'Quiz 1', 'earned': 0, 'possible': 10},
        ]}}
        assert service._component_scores_from_snapshot(snapshot)[0]['earned'] == 0

    read()
    assert current_component_read_cache() is None


def test_read_cache_is_cleared_on_failure_and_never_reused_by_another_service(monkeypatch):
    services = [AcademicService(None), AcademicService(None)]
    snapshot = SimpleNamespace(raw_json={'payload': {'component_scores': [
        {'name': 'Quiz 1', 'earned': 10, 'possible': 10},
    ]}})
    counts = [0, 0]
    for index, service in enumerate(services):
        original = service._component_scores_from_payload
        def normalize(payload, index=index, original=original):
            counts[index] += 1
            return original(payload)
        monkeypatch.setattr(service, '_component_scores_from_payload', normalize)

    @snapshot_component_read_scope
    def fail():
        for service in services:
            service._component_scores_from_snapshot(snapshot)
            service._component_scores_from_snapshot(snapshot)
        raise RuntimeError('failed read')

    with pytest.raises(RuntimeError, match='failed read'):
        fail()
    assert counts == [1, 1]
    assert current_component_read_cache() is None
    services[0]._component_scores_from_snapshot(snapshot)
    assert counts == [2, 1]
