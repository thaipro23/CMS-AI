from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_teacher_management_requests_lite_teacher_rows_by_default() -> None:
    api = read('frontend/lib/api.ts')
    page = read('frontend/app/teacher-management/page.tsx')
    detail = read('frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx')
    route = read('backend/app/api/routes/academic.py')
    service = read('backend/app/services/academic_service.py')

    assert 'includeClasses?: boolean' in api
    assert 'params.set("include_classes"' in api
    assert 'includeClasses: false' in page
    assert 'includeClasses: true' in detail
    assert 'include_classes: bool = Query(False' in route
    assert 'use_cache=not fresh' in route
    assert 'def _teacher_report_public_item' in service
    assert "payload.pop('classes', None)" in service


def test_notices_are_typed_and_action_buttons_equalized() -> None:
    css = read('frontend/app/globals.css')
    student_page = read('frontend/app/student-management/page.tsx')
    teacher_page = read('frontend/app/teacher-management/page.tsx')

    assert '.academic-inline-notice.success' in css
    assert '.academic-inline-notice.error' in css
    assert '.subject-table .row-actions .btn' in css
    assert 'width: 100%' in css
    assert 'InlineNotice' in student_page
    assert 'noticeSuccess' in student_page
    assert 'InlineNotice' in teacher_page
    assert 'noticeError' in teacher_page
