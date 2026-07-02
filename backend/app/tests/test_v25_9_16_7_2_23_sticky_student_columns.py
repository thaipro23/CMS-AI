from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_class_detail_student_table_locks_stt_and_student_columns_together():
    source = read('frontend/app/student-management/classes/[classId]/page.tsx')
    assert 'student-grade-table two-col-sticky-table' in source
    assert 'className="stt-col sticky-index-col"' in source
    assert 'className="sticky-col student-sticky-col"' in source
    assert 'className="stt-cell sticky-index-col"' in source
    assert 'sticky-col student-sticky-col compact-student-identity-cell' in source


def test_learning_behavior_result_table_uses_same_two_column_sticky_pattern():
    source = read('frontend/app/analytics/learning/page.tsx')
    assert 'analytics-result-table two-col-sticky-table analytics-two-col-sticky-table' in source
    assert 'className="stt-col sticky-index-col"' in source
    assert 'className="student-sticky-col"' in source
    assert 'className="stt-cell sticky-index-col"' in source
    assert 'analytics-student-identity-cell' in source


def test_css_overrides_old_single_left_zero_rule_for_student_column():
    css = read('frontend/app/globals.css')
    assert 'v25.9.16.7.2.23 — keep STT + Sinh viên locked together' in css
    assert '--sticky-stt-width: 56px' in css
    assert 'left: var(--sticky-stt-width) !important' in css
    assert '.class-student-table-scroll .student-grade-table.two-col-sticky-table .sticky-col.student-sticky-col' in css
