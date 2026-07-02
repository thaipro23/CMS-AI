from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_teacher_management_no_manual_report_refresh_or_cache_notice() -> None:
    source = read('frontend/app/teacher-management/page.tsx')
    forbidden = [
        'Tải lại báo cáo',
        'Tính lại báo cáo',
        '<b>Báo cáo:</b>',
        '<b>Cách đọc số liệu:</b>',
        'GV theo bộ lọc',
        'Lượt lớp phân công',
        'Lượt SV theo phân công',
        'createAcademicTrainingTeacherCacheJob',
    ]
    for text in forbidden:
        assert text not in source

    assert 'Quản lý giảng viên' in source
    assert 'Tổng giảng viên' in source
    assert 'Tổng số lớp' in source
    assert 'Tổng số sinh viên' in source
    assert 'Xuất Excel nền' in source


def test_student_management_total_kpi_labels_are_plain() -> None:
    source = read('frontend/app/student-management/page.tsx')
    forbidden = [
        'Môn theo bộ lọc',
        'Lớp theo bộ lọc',
        'Sinh viên theo bộ lọc</span>',
        'Cảnh báo theo bộ lọc',
        '<b>Cách đọc số liệu:</b>',
    ]
    for text in forbidden:
        assert text not in source

    assert 'Tổng số môn' in source
    assert 'Tổng số lớp' in source
    assert 'Tổng số sinh viên theo bộ lọc' in source
    assert 'Course CMS đã map' in source
    assert 'Cần kiểm tra' in source


def test_teacher_report_endpoint_bypasses_stale_cache_for_dynamic_counts() -> None:
    source = read('backend/app/api/routes/academic.py')
    route_start = source.index("@router.get('/training/teachers')")
    route_end = source.index("@router.get('/training/teachers/export')")
    route = source[route_start:route_end]
    assert 'use_cache=False' in route
