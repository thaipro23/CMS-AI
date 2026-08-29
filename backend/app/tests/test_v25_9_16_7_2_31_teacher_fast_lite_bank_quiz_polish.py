from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_teacher_management_has_fast_lite_report_path():
    source = (ROOT / 'backend/app/services/academic_service.py').read_text()
    assert 'def _training_teacher_report_lite_fast(' in source
    assert "'cache': {" in source
    assert "'status': 'lite'" in source
    assert 'avoids hydrating nested classes' in source
    assert 'not include_all and not include_students and not include_classes and not teacher_id' in source


def test_bank_quiz_uses_explicit_notice_tone_not_keyword_heuristic():
    page = (ROOT / 'frontend/app/bank/quiz/page.tsx').read_text()
    assert 'type InlineMessage' in page
    assert 'messageClass(message)' in page
    assert 'isErrorMessage' not in page
    assert 'inlineMessageFromBackend(result' in page
    assert "lower.includes('không')" not in page


def test_bank_quiz_status_cell_has_spacing_container():
    page = (ROOT / 'frontend/app/bank/quiz/page.tsx').read_text()
    css = (ROOT / 'frontend/app/globals.css').read_text()
    assert 'className="quiz-status-cell"' in page
    assert 'className="quiz-status-control"' in page
    assert "return 'Bỏ qua'" in page
    assert 'v25.9.16.7.2.31 — bank quiz spacing and semantic notice colors' in css
    assert '.bank-quiz-page .quiz-status-control' in css
    assert 'gap: 7px' in css
    assert '.bank-quiz-page .quiz-inline-message.danger' in css
    assert '.bank-quiz-page .quiz-inline-message.info' in css
