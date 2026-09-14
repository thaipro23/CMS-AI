from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.academic.sync_enrollment import _preserve_confirmed_enrollment_for_learning


ROOT = Path(__file__).resolve().parents[3]


def _snapshot(*, status: str = 'enrolled', synced: bool = True, mode: str | None = 'audit'):
    return SimpleNamespace(
        enrollment_status=status,
        enrollment_synced_at=datetime(2026, 9, 14, 5, 0, 0) if synced else None,
        enrollment_mode=mode,
    )


def test_unknown_learning_result_cannot_downgrade_confirmed_enrollment():
    result = _preserve_confirmed_enrollment_for_learning(
        _snapshot(),
        {
            'student_code': 'PH12345',
            'enrollment_status': 'unknown',
            'note': 'Plugin không trả dữ liệu học tập cho sinh viên này',
        },
    )

    assert result['enrollment_status'] == 'enrolled'
    assert result['enrollment_mode'] == 'audit'
    assert result['learning_analytics_enrollment_status'] == 'unknown'
    assert result['enrollment_preserved_from_snapshot'] is True


def test_missing_learning_enrollment_fields_preserve_confirmed_enrollment():
    result = _preserve_confirmed_enrollment_for_learning(
        _snapshot(mode='honor'),
        {'student_code': 'PH12345', 'progress_percent': 25.0},
    )

    assert result['enrollment_status'] == 'enrolled'
    assert result['enrollment_mode'] == 'honor'
    assert result['learning_analytics_enrollment_status'] is None
    assert result['enrollment_preserved_from_snapshot'] is True


def test_explicit_negative_learning_enrollment_is_not_hidden():
    result = _preserve_confirmed_enrollment_for_learning(
        _snapshot(),
        {
            'student_code': 'PH12345',
            'enrollment_status': 'not_enrolled',
            'is_enrolled': False,
        },
    )

    assert result['enrollment_status'] == 'not_enrolled'
    assert result.get('enrollment_preserved_from_snapshot') is not True


def test_unconfirmed_snapshot_is_not_promoted_to_enrolled():
    result = _preserve_confirmed_enrollment_for_learning(
        _snapshot(status='unknown', synced=False),
        {'student_code': 'PH12345', 'enrollment_status': 'unknown'},
    )

    assert result['enrollment_status'] == 'unknown'
    assert result.get('enrollment_preserved_from_snapshot') is not True


def test_learning_sync_observes_connector_before_preserving_local_enrollment_truth():
    source = (ROOT / 'backend/app/services/academic/sync_enrollment.py').read_text(encoding='utf-8')
    learning = source.split('def sync_class_learning_insight(', 1)[1].split('def _try_auto_map_course_for_class(', 1)[0]
    observed = 'connector_enrolled_seen += 1'
    guarded = 'result = _preserve_confirmed_enrollment_for_learning(_snapshot, result)'
    persisted = 'self._upsert_learning_snapshot('

    assert observed in learning
    assert guarded in learning
    assert persisted in learning
    assert learning.index(observed) < learning.index(guarded) < learning.index(persisted)
