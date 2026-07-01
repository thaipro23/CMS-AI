from types import SimpleNamespace
from pathlib import Path

import pytest

pytest.importorskip("jose")

from app.services.academic_service import AcademicService


def _service() -> AcademicService:
    return AcademicService.__new__(AcademicService)


def test_learning_sync_flow_is_read_only_and_does_not_auto_enroll():
    root = Path(__file__).resolve().parents[2]
    text = (root / 'services' / 'academic_service.py').read_text(encoding='utf-8')
    start = text.index('    def sync_class_learning_insight(')
    end = text.index('    def _try_auto_map_course_for_class', start)
    body = text[start:end]

    assert 'sync_class_course_enrollment(' not in body
    assert 'Cập nhật điểm is read-only' in body


def test_course_home_completion_summary_is_official_progress_source():
    service = _service()
    snapshot = SimpleNamespace(
        progress_percent=None,
        grade_percent=None,
        completed_blocks=None,
        total_blocks=None,
        enrollment_status='enrolled',
        learning_synced_at=None,
        last_synced_at=None,
        raw_json={
            'payload': {
                'progress_percent': 12.5,
                'progress_source': 'CourseHomeProgressRoute:completion_summary',
                'progress': {
                    'source': 'CourseHomeProgressRoute:completion_summary',
                    'payload': {'completion_summary': {'complete_count': 1, 'incomplete_count': 7}},
                },
                'grade_percent': 70,
                'component_scores': [{'name': 'Quiz 1', 'percent': 100}],
            }
        },
    )
    mapping = SimpleNamespace(match_status='matched')

    assert service._snapshot_progress_percent(snapshot) == 12.5
    diagnostic = service._learning_snapshot_diagnostics(snapshot, mapping)
    assert diagnostic['official_progress'] is True
    assert diagnostic['has_progress_percent'] is True
    assert diagnostic['has_grade_percent'] is True
    assert diagnostic['has_component_grades'] is True


def test_non_official_progress_is_kept_na_to_avoid_false_completion():
    service = _service()
    snapshot = SimpleNamespace(
        progress_percent=88,
        grade_percent=90,
        completed_blocks=8,
        total_blocks=10,
        enrollment_status='enrolled',
        learning_synced_at=None,
        last_synced_at=None,
        raw_json={'payload': {'grade_percent': 90, 'component_scores': [{'name': 'Quiz 1', 'percent': 100}]}},
    )
    mapping = SimpleNamespace(match_status='matched')

    assert service._snapshot_progress_percent(snapshot) is None
    diagnostic = service._learning_snapshot_diagnostics(snapshot, mapping)
    assert diagnostic['official_progress'] is False
    assert diagnostic['has_progress_percent'] is False
    assert 'không trả Course Home Progress official' in diagnostic['note']


def test_student_module_fallback_counts_are_accepted_for_completion():
    service = _service()
    snapshot = SimpleNamespace(
        progress_percent=None,
        grade_percent=None,
        completed_blocks=15,
        total_blocks=70,
        enrollment_status='enrolled',
        learning_synced_at=None,
        last_synced_at=None,
        raw_json={
            'payload': {
                'progress_percent': None,
                'progress_source': 'StudentModule',
                'completed_blocks': 15,
                'total_blocks': 70,
                'progress': {
                    'source': 'StudentModule',
                    'completed_blocks': 15,
                    'total_blocks': 70,
                    'has_student_module_fallback': True,
                    'fallback_reason': 'course_home_progress_unavailable_student_module_counts',
                },
            }
        },
    )
    mapping = SimpleNamespace(match_status='matched')

    assert service._snapshot_progress_percent(snapshot) == 21.43
    diagnostic = service._learning_snapshot_diagnostics(snapshot, mapping)
    assert diagnostic['official_progress'] is False
    assert diagnostic['student_module_progress'] is True
    assert diagnostic['completed_blocks'] == 15
    assert diagnostic['total_blocks'] == 70
    assert diagnostic['has_progress_percent'] is True
    assert 'StudentModule' in diagnostic['note']
