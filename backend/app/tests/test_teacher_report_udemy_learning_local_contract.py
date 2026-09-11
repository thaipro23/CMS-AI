from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
TEACHER_REPORT = ROOT / 'backend/app/services/academic/teacher_report.py'


class TeacherReportUdemyLearningLocalContractTest(unittest.TestCase):
    def test_udemy_class_initializes_learning_payload_before_platform_branch(self):
        """Udemy-only teacher drill-down must not read an unbound CMS `learning` local."""
        source = TEACHER_REPORT.read_text(encoding='utf-8')
        expected = (
            "            alerts: list[str] = []\n"
            "            learning: dict[str, Any] = {}\n"
            "            if is_udemy:\n"
        )
        self.assertIn(
            expected,
            source,
            'training_teacher_report must initialize learning={} before the Udemy/CMS branch',
        )

    def test_class_payload_can_safely_read_learning_component_summaries(self):
        source = TEACHER_REPORT.read_text(encoding='utf-8')
        self.assertIn("'learning_component_summaries': learning.get('learning_component_summaries') or []", source)


if __name__ == '__main__':
    unittest.main()
