from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_teacher_management_has_fast_lite_report_path():
    service = (ROOT / 'backend/app/services/academic_service.py').read_text()
    workflow = (ROOT / 'backend/app/services/academic/teacher_report.py').read_text()
    assert 'def _training_teacher_report_lite_fast(' in service
    assert "'cache': {" in workflow
    assert "'status': 'lite'" in workflow
    assert 'avoids hydrating nested classes' in workflow
    assert 'not include_all and not include_students and not include_classes and not teacher_id' in workflow


def test_teacher_management_lite_pages_teachers_before_hydrating_learning_rows():
    source = (ROOT / 'backend/app/services/academic/teacher_report.py').read_text()
    body = source.split('def _training_teacher_report_lite_fast(', 1)[1].split('def _training_teacher_report_from_cache(', 1)[0]

    assert 'teacher_scope_query =' in body
    assert '.offset((page - 1) * page_size)' in body
    assert '.limit(page_size)' in body
    assert 'AcademicTeacher.id.in_(page_teacher_ids)' in body
    assert 'summary = self._training_teacher_report_lite_scope_summary(' in body
    assert body.index('page_teacher_ids =') < body.index('rows = query.filter(')
    assert body.index('rows = query.filter(') < body.index('class_ids = list(class_by_id.keys())')


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
