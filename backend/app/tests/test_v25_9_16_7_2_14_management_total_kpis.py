from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_subject_management_api_exposes_filter_summary():
    schema = read('backend/app/schemas/academic.py')
    service = read('backend/app/services/academic_service.py')

    assert 'class AcademicSubjectManagementSummaryOut' in schema
    assert 'summary: AcademicSubjectManagementSummaryOut' in schema
    assert 'class_count: int = 0' in schema
    assert 'student_count: int = 0' in schema
    assert 'alert_subject_count: int = 0' in schema

    assert 'all_rows = ordered.all()' in service
    assert "'class_count': int(sum(item.get('class_count') or 0 for item in summary_source))" in service
    assert "'student_count': int(sum(item.get('student_count') or 0 for item in summary_source))" in service
    assert "'summary': summary" in service


def test_student_management_uses_total_kpis_not_current_page_wording():
    page = read('frontend/app/student-management/page.tsx')
    types = read('frontend/types/index.ts')

    assert 'AcademicSubjectManagementSummary' in types
    assert 'summary?: AcademicSubjectManagementSummary' in types
    assert 'const [summary, setSummary]' in page
    assert 'setSummary(normalizeSubjectSummary(result.summary))' in page
    assert 'Lớp theo bộ lọc' in page
    assert 'Sinh viên theo bộ lọc' in page
    assert 'Course CMS đã map' in page
    assert 'KPI phía trên đã là tổng toàn bộ bộ lọc' in page
    assert 'Lớp trong trang' not in page
    assert 'Sinh viên trong trang' not in page
    assert 'Course CMS trong trang' not in page


def test_teacher_management_titles_are_scope_explicit():
    page = read('frontend/app/teacher-management/page.tsx')

    assert 'Báo cáo giảng viên theo phân công' in page
    assert 'GV theo bộ lọc' in page
    assert 'Lượt lớp phân công' in page
    assert 'Lượt SV theo phân công' in page
    assert 'KPI là tổng theo bộ lọc khi cache sẵn sàng' in page
