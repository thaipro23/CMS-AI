from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
TEACHER_REPORT = ROOT / 'backend/app/services/academic/teacher_report.py'


class TeacherReportOuterjoinContractTest(unittest.TestCase):
    def test_teacher_report_has_no_outerjoin_with_more_than_target_and_onclause(self):
        """SQLAlchemy Query.outerjoin accepts target and an optional onclause only."""
        source = TEACHER_REPORT.read_text(encoding='utf-8')
        tree = ast.parse(source)
        invalid_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'outerjoin'
            and len(node.args) > 2
        ]
        self.assertFalse(
            invalid_calls,
            'teacher_report.py contains Query.outerjoin(...) with too many positional arguments',
        )

    def test_student_watch_query_does_not_select_unused_udemy_snapshot_entity(self):
        """The student watch export only consumes the Open edX mapping in this query."""
        source = TEACHER_REPORT.read_text(encoding='utf-8')
        start_marker = 'if include_students and class_ids:'
        end_marker = 'for class_id, class_student_meta, student, mapping in student_query'
        self.assertIn(start_marker, source)
        self.assertIn(end_marker, source)
        watch_query = source.split(start_marker, 1)[1].split(end_marker, 1)[0]
        self.assertNotIn('UdemyStudentProgress', watch_query)


if __name__ == '__main__':
    unittest.main()
