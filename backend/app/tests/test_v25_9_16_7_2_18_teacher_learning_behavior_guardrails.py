from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / 'frontend/app/analytics/learning/page.tsx'
API = ROOT / 'frontend/lib/api.ts'
TYPES = ROOT / 'frontend/types/index.ts'
SERVICE = ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py'


def test_learning_page_does_not_send_invalid_academic_page_size_500():
    text = PAGE.read_text(encoding='utf-8')
    assert 'pageSize: 500' not in text
    assert 'API_PAGE_SIZE = 200' in text
    assert 'loadAllSubjects' in text
    assert 'getAcademicSubjectClasses' not in text


def test_academic_api_client_clamps_page_size_to_backend_limit():
    text = API.read_text(encoding='utf-8')
    assert 'function clampAcademicPageSize' in text
    assert 'Math.min(200' in text
    assert "params.set('page_size', String(clampAcademicPageSize(filters.pageSize)))" in text


def test_class_overview_carries_effective_course_mapping_for_student_detail():
    service = SERVICE.read_text(encoding='utf-8')
    types = TYPES.read_text(encoding='utf-8')
    page = PAGE.read_text(encoding='utf-8')
    assert 'override_by_class' in service
    assert 'inherited_by_class = AcademicService(self.db).inherited_course_mappings_for_classes(classes)' in service
    assert "'openedx_course_id': mapping.openedx_course_id if mapping else None" in service
    assert 'openedx_course_id?: string | null' in types
    assert 'selectedClassOverview?.openedx_course_id' in page


def test_teacher_management_view_is_result_first_and_compact():
    text = PAGE.read_text(encoding='utf-8')
    assert 'Giáo viên chọn kỳ, cơ sở, môn rồi xem từng lớp' in text
    assert 'Danh sách lớp cần quản lý' in text
    assert '<th>Cần xem</th>' in text
    assert '<th>Treo máy</th>' not in text
    assert '<th>Bất thường</th>' not in text
    assert 'Lý do ra kết quả' in text
