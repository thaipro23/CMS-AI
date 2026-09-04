from types import SimpleNamespace

from app.services.academic_service import AcademicService


def _service() -> AcademicService:
    service = AcademicService.__new__(AcademicService)
    service._snapshot_has_learning_activity = lambda snapshot: bool(snapshot.active)
    service._snapshot_progress_percent = lambda snapshot: snapshot.progress
    service._snapshot_grade_percent = lambda snapshot: snapshot.grade
    service._low_progress_threshold = lambda: 50.0
    service._low_grade_threshold = lambda: 50.0
    return service


def _snapshot(*, enrollment='enrolled', active=True, progress=80.0, grade=80.0):
    return SimpleNamespace(
        enrollment_status=enrollment,
        active=active,
        progress=progress,
        grade=grade,
    )


def test_issue_counts_are_per_student_not_subject_average():
    service = _service()
    counts = service._learning_issue_counts_from_snapshots([
        _snapshot(enrollment='not_enrolled', active=False, progress=None, grade=None),
        _snapshot(active=False, progress=0.0, grade=None),
        _snapshot(active=True, progress=35.0, grade=85.0),
        _snapshot(active=True, progress=90.0, grade=40.0),
        _snapshot(active=True, progress=90.0, grade=90.0),
    ])
    assert counts == {
        'not_enrolled': 1,
        'no_activity': 1,
        'low_progress': 1,
        'low_grade': 1,
        'sync_error': 0,
    }


def test_missing_or_failed_sync_is_not_misreported_as_not_enrolled():
    service = _service()
    counts = service._learning_issue_counts_from_snapshots([
        _snapshot(enrollment='unknown', active=False, progress=None, grade=None),
        _snapshot(enrollment='failed', active=False, progress=None, grade=None),
    ])
    assert counts['not_enrolled'] == 0
    assert counts['sync_error'] == 2


def test_subject_filter_matches_when_any_student_has_issue_even_if_averages_are_good():
    service = _service()
    entry = {
        'student_count': 30,
        'learning_enrolled_count': 29,
        'learning_synced_count': 30,
        'learning_active_count': 29,
        'learning_avg_progress_percent': 88.0,
        'learning_avg_grade_percent': 82.0,
        'learning_alerts': [],
        'learning_status_counts': {
            'not_enrolled': 1,
            'no_activity': 1,
            'low_progress': 1,
            'low_grade': 1,
            'sync_error': 0,
        },
    }
    assert service._entry_matches_learning_list_filter(entry, 'not_fully_enrolled') is True
    assert service._entry_matches_learning_list_filter(entry, 'no_activity') is True
    assert service._entry_matches_learning_list_filter(entry, 'low_progress') is True
    assert service._entry_matches_learning_list_filter(entry, 'low_grade') is True


def test_subject_filter_does_not_treat_missing_snapshot_as_known_not_enrolled():
    service = _service()
    entry = {
        'student_count': 30,
        'learning_enrolled_count': 20,
        'learning_synced_count': 20,
        'learning_active_count': 20,
        'learning_avg_progress_percent': 80.0,
        'learning_avg_grade_percent': 80.0,
        'learning_alerts': ['Chưa có dữ liệu học tập'],
        'learning_status_counts': {
            'not_enrolled': 0,
            'no_activity': 0,
            'low_progress': 0,
            'low_grade': 0,
            'sync_error': 0,
        },
    }
    assert service._entry_matches_learning_list_filter(entry, 'not_fully_enrolled') is False
