from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class PrimaryAfterEnrollmentPolicyTests(unittest.TestCase):
    def test_only_immediate_post_enrollment_read_requests_primary(self):
        from app.services.academic.analytics_read_consistency import class_analytics_read_consistency

        self.assertEqual(
            class_analytics_read_consistency(immediate_after_enrollment=True),
            'primary_after_enrollment',
        )
        self.assertEqual(class_analytics_read_consistency(immediate_after_enrollment=False), 'replica')

    def test_primary_response_must_be_connector_confirmed(self):
        from app.services.academic.analytics_read_consistency import validate_analytics_read_consistency

        with self.assertRaisesRegex(RuntimeError, 'primary'):
            validate_analytics_read_consistency(
                {'read_consistency': 'replica'},
                requested='primary_after_enrollment',
            )
        validate_analytics_read_consistency(
            {'read_consistency': 'primary_after_enrollment'},
            requested='primary_after_enrollment',
        )

    def test_normal_replica_response_remains_compatible(self):
        from app.services.academic.analytics_read_consistency import validate_analytics_read_consistency

        validate_analytics_read_consistency({}, requested='replica')

    def test_full_flow_is_the_only_caller_enabling_primary(self):
        app_root = BACKEND / 'app'
        workflow = (app_root / 'services' / 'academic' / 'sync_enrollment.py').read_text(encoding='utf-8')
        client = (app_root / 'services' / 'openedx_student_insight.py').read_text(encoding='utf-8')

        learning_start = workflow.index('def sync_class_learning_insight(')
        full_start = workflow.index('def sync_class_full_cms_flow(')
        learning_body = workflow[learning_start:full_start]
        full_body = workflow[full_start:]
        self.assertIn('immediate_after_enrollment: bool = False', learning_body)
        self.assertIn('read_consistency=read_consistency', learning_body)
        self.assertIn('immediate_after_enrollment=True', full_body)
        self.assertIn("'read_consistency': read_consistency", client)


if __name__ == '__main__':
    unittest.main()
