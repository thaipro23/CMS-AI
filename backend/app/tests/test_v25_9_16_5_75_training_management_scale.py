import pytest

pytest.importorskip("jose")

from app.services.academic_service import AcademicService


def test_training_risk_count_is_bounded_and_ignores_insufficient_data():
    status_counts = {
        'not_enrolled': 80,
        'exam_insufficient_data': 52806,
        'deadline_late': 39,
        'low_grade': 20,
    }

    assert AcademicService._bounded_risk_count_from_status_counts(status_counts, 2868) == 80


def test_training_risk_count_never_exceeds_student_count():
    status_counts = {
        'not_enrolled': 120,
        'deadline_late': 90,
        'low_grade': 70,
    }

    assert AcademicService._bounded_risk_count_from_status_counts(status_counts, 100) == 100
