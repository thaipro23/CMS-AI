from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_class_detail_back_preserves_all_campus_list_scope():
    source = read('frontend/app/student-management/classes/[classId]/page.tsx')
    assert "searchParams.get('list_campus')" in source
    assert "listCampusParam !== 'all'" in source
    assert "const classCampus = classInfo?.campus" in source
    assert "behaviorParams.set('campus', classCampus)" in source


def test_subject_class_links_carry_list_scope_and_show_behavior_action():
    source = read('frontend/app/student-management/subjects/[subjectId]/classes/page.tsx')
    assert "detailParams.set('list_campus', campus || 'all')" in source
    assert "Tất cả cơ sở" in source
    assert "Không phụ thuộc trang đang xem" in source
    assert "Hành vi học" in source
    assert "summary.course_mapped_count" in source


def test_teacher_management_does_not_autoselect_first_campus_and_reads_url():
    source = read('frontend/app/teacher-management/page.tsx')
    assert "useSearchParams" in source
    assert "searchParams.get('campus') === 'all'" in source
    assert "return ''" in source
    assert "return data[0]?.campus_code" not in source


def test_backend_class_and_teacher_kpis_are_full_filter_not_current_page():
    source = read('backend/app/services/academic_service.py')
    assert "KPI cards must be calculated from the full current filter" in source
    assert "summary = {\n            'class_count': int(total)" in source
    assert "fast_page_mode = False" in source
    assert "one-campus totals look larger than all-campus totals" in source
