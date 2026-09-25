from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def _service_without_db() -> LearningAnalyticsCoreService:
    return object.__new__(LearningAnalyticsCoreService)


def test_blank_course_mapping_scope_is_wildcard_for_classes():
    service = _service_without_db()
    query = MagicMock()
    column = MagicMock()

    result = service._class_scope_filter(query, column, None)
    assert result is query
    query.filter.assert_not_called()

    result = service._class_scope_filter(query, column, "")
    assert result is query
    query.filter.assert_not_called()


def test_non_blank_course_mapping_scope_remains_exact_match():
    service = _service_without_db()
    query = MagicMock()
    filtered = MagicMock()
    query.filter.return_value = filtered
    column = MagicMock()
    predicate = column.__eq__.return_value

    result = service._class_scope_filter(query, column, "HN")

    assert result is filtered
    query.filter.assert_called_once_with(predicate)


def test_specific_scope_outranks_wildcard_scope():
    service = _service_without_db()
    klass = SimpleNamespace(
        term_id="term-fa26",
        subject_id="subject-com109",
        block_id="block-1",
        campus="HN",
        branch="poly",
    )
    broad = SimpleNamespace(
        term_id="term-fa26",
        subject_id="subject-com109",
        block_id=None,
        campus=None,
        branch=None,
    )
    specific = SimpleNamespace(
        term_id="term-fa26",
        subject_id="subject-com109",
        block_id="block-1",
        campus="HN",
        branch="poly",
    )

    broad_score = service._subject_mapping_score_for_class(broad, klass)
    specific_score = service._subject_mapping_score_for_class(specific, klass)

    assert broad_score == 41
    assert specific_score == 80
    assert specific_score > broad_score


def test_mismatched_non_blank_scope_is_ineligible():
    service = _service_without_db()
    klass = SimpleNamespace(
        term_id="term-fa26",
        subject_id="subject-com109",
        block_id="block-1",
        campus="HN",
        branch="poly",
    )
    wrong_campus = SimpleNamespace(
        term_id="term-fa26",
        subject_id="subject-com109",
        block_id=None,
        campus="HCM",
        branch=None,
    )

    assert service._subject_mapping_score_for_class(wrong_campus, klass) is None


def test_quiz_recalculation_does_not_depend_on_session_structure():
    service = _service_without_db()
    service.recalculate_course_quiz_attempts = MagicMock(
        return_value={"course_id": "course-v1:FPL+COM109+FA26", "quiz_attempt_rows": 7}
    )
    service.get_session_structure = MagicMock(return_value=[])

    result = service.recalculate_student_session_progress(
        class_id="class-1",
        course_id="course-v1:FPL+COM109+FA26",
    )

    service.recalculate_course_quiz_attempts.assert_called_once_with(
        course_id="course-v1:FPL+COM109+FA26",
        username=None,
        class_id="class-1",
    )
    assert result["sessions"] == 0
    assert result["quiz"]["quiz_attempt_rows"] == 7
    assert "Quiz analytics" in result["message"]
