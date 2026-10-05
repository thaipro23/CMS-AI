from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class PrimaryAfterEnrollmentPolicyTests(unittest.TestCase):
    def test_score_sync_facade_preserves_read_consistency_for_worker_and_api(self):
        from app.services.academic.analytics_read_consistency import class_analytics_read_consistency
        from app.services.academic.sync_enrollment import AcademicSyncEnrollmentWorkflowService
        from app.services.academic_service import AcademicService

        # Isolate database/CMS I/O while exercising the real public entry point
        # and the real read policy. Dropping the flag would read stale replicas
        # immediately after enrollment; rejecting it crashes even manual jobs.
        def observe_read_policy(workflow, user, class_id, *, force=False, limit=1000, immediate_after_enrollment=False):
            return {
                'read_consistency': class_analytics_read_consistency(
                    immediate_after_enrollment=immediate_after_enrollment,
                ),
                'class_id': class_id,
                'force': force,
                'limit': limit,
            }

        service = AcademicService(None)
        with patch.object(AcademicSyncEnrollmentWorkflowService, 'sync_class_learning_insight', observe_read_policy):
            for kwargs, expected in (
                ({'immediate_after_enrollment': True}, 'primary_after_enrollment'),
                ({'immediate_after_enrollment': False}, 'replica'),
                ({}, 'replica'),
            ):
                with self.subTest(kwargs=kwargs):
                    result = service.sync_class_learning_insight(
                        None, 'class-1', force=True, limit=250, **kwargs,
                    )
                    self.assertEqual(result, {
                        'read_consistency': expected,
                        'class_id': 'class-1',
                        'force': True,
                        'limit': 250,
                    })

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
