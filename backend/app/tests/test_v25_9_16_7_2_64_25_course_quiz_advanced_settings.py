from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_connector_enforces_course_wide_quiz_advanced_settings():
    source = (ROOT / "openedx-connector-plugin/openedx_ai_connector/studio.py").read_text(encoding="utf-8")
    assert "def _ensure_course_quiz_policy" in source
    assert "'max_attempts': 1" in source
    assert "'showanswer': 'never'" in source
    assert "course_quiz_policy_result = _ensure_course_quiz_policy" in source
    assert "'course_quiz_policy_result': course_quiz_policy_result" in source


def test_quiz_workflow_requires_verified_course_policy():
    source = (ROOT / "backend/app/services/question_bank/quiz_creation.py").read_text(encoding="utf-8")
    assert "course_policy_result.get('verified') is True" in source
    assert "course_policy_after.get('max_attempts') == 1" in source
    assert "str(course_policy_after.get('showanswer') or '').lower() == 'never'" in source
