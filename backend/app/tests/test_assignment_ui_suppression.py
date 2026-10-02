from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]


def test_class_exam_column_does_not_render_assignment_score():
    page = (ROOT / 'frontend/app/student-management/classes/[classId]/page.tsx').read_text(encoding='utf-8')
    start = page.index("{ key: 'exam', header: 'Điều kiện thi'")
    end = page.index("...componentColumns.map", start)
    rendered_exam_column = re.sub(r'\{/\*.*?\*/\}', '', page[start:end], flags=re.DOTALL)

    assert 'ACMS_ASSIGNMENT_SCORE_DISPLAY_DISABLED_2026_10_02' in page[start:end]
    assert '<small>Assignment:' not in rendered_exam_column
