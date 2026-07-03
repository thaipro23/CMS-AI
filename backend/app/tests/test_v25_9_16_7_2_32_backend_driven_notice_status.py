from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_quiz_backend_responses_expose_ui_status_fields():
    schema = (ROOT / "backend/app/schemas/question_bank.py").read_text()
    service = (ROOT / "backend/app/services/question_bank_service.py").read_text()
    assert "class BackendUiStatusMixin" in schema
    assert "ui_status: Literal['success', 'error', 'warning', 'info']" in schema
    assert "class QuizAutoMapOut(BackendUiStatusMixin)" in schema
    assert "class BankReleaseQuizCreateOut(BackendUiStatusMixin)" in schema
    assert "class CourseQuizRollbackOut(BackendUiStatusMixin)" in schema
    assert "def _ui_notice(" in service
    assert "**_ui_notice('success', saved_message)" in service
    assert "**_ui_notice(ui_status, ui_message)" in service


def test_bank_quiz_frontend_uses_backend_ui_status_not_message_text():
    page = (ROOT / "frontend/app/bank/quiz/page.tsx").read_text()
    helper = (ROOT / "frontend/lib/backendNotice.ts").read_text()
    assert "inlineMessageFromBackend(result" in page
    assert "result.ui_status" not in page  # page must use one centralized helper, not ad-hoc parsing
    assert "ui_status" in helper
    assert "normalizeUiStatus" in helper
    assert "includes('không')" not in page
    assert 'includes("không")' not in page


def test_types_include_backend_ui_notice_contract():
    types = (ROOT / "frontend/types/index.ts").read_text()
    assert "export type BackendUiNotice" in types
    assert "export type QuizAutoMapResult = BackendUiNotice &" in types
    assert "export type BankReleaseQuizCreateResult = BackendUiNotice &" in types
    assert "export type CourseQuizRollbackResult = BackendUiNotice &" in types
