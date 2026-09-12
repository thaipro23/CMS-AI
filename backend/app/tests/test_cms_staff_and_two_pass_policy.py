from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class CmsStaffPolicyTests(unittest.TestCase):
    def test_only_campus_owner_requires_global_cms_staff(self):
        from app.services.cms_staff_policy import cms_staff_required_for_role

        self.assertTrue(cms_staff_required_for_role('CAMPUS_OWNER'))
        for role_code in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'TEACHER_ASSIGNED'):
            with self.subTest(role_code=role_code):
                self.assertFalse(cms_staff_required_for_role(role_code))

    def test_required_staff_must_be_connector_verified(self):
        from app.services.cms_staff_policy import validate_cms_provisioning

        with self.assertRaisesRegex(RuntimeError, 'staff'):
            validate_cms_provisioning({'exists': True, 'user_profile_ok': True, 'is_staff': False}, require_staff=True)

        verified = validate_cms_provisioning(
            {'exists': True, 'user_profile_ok': True, 'is_staff': True, 'is_superuser': False},
            require_staff=True,
        )
        self.assertTrue(verified['is_staff'])
        self.assertFalse(verified['is_superuser'])


class FullCmsTwoPassPolicyTests(unittest.TestCase):
    def test_learning_followup_is_a_separate_delayed_replica_job(self):
        from app.services.academic.two_pass_sync import build_learning_sync_followup

        followup = build_learning_sync_followup(
            requested_by='operator',
            class_id='class-1',
            force=True,
            limit=500,
            requester_context={'user_id': 'operator', 'role': 'viewer'},
            parent_job_id='full-job-1',
            delay_seconds=60,
        )

        self.assertEqual(followup['job_type'], 'learning_sync')
        self.assertEqual(followup['status'], 'queued')
        self.assertEqual(followup['countdown'], 60)
        self.assertEqual(followup['class_id'], 'class-1')
        self.assertEqual(followup['request_json']['parent_job_type'], 'full_cms_sync')
        self.assertEqual(followup['request_json']['parent_job_id'], 'full-job-1')
        self.assertTrue(followup['request_json']['delayed_after_enrollment'])
        self.assertEqual(followup['request_json']['approved_class_id'], 'class-1')

    def test_followup_delay_is_bounded(self):
        from app.services.academic.two_pass_sync import build_learning_sync_followup

        low = build_learning_sync_followup(
            requested_by='operator', class_id='class-1', force=False, limit=500,
            requester_context={}, parent_job_id=None, delay_seconds=0,
        )
        high = build_learning_sync_followup(
            requested_by='operator', class_id='class-1', force=False, limit=500,
            requester_context={}, parent_job_id=None, delay_seconds=9999,
        )
        self.assertEqual(low['countdown'], 10)
        self.assertEqual(high['countdown'], 900)

    def test_followup_keeps_the_configured_full_roster_limit(self):
        from app.services.academic.two_pass_sync import build_learning_sync_followup

        followup = build_learning_sync_followup(
            requested_by='operator', class_id='class-1', force=False, limit=5000,
            requester_context={}, parent_job_id='full-job-1', delay_seconds=60,
        )
        self.assertEqual(followup['limit'], 5000)
        self.assertEqual(followup['request_json']['limit'], 5000)

    def test_followup_runs_only_after_a_completed_enrollment_pass(self):
        from app.services.academic.two_pass_sync import should_enqueue_learning_followup

        self.assertTrue(should_enqueue_learning_followup(requested=True, enabled=True, flow_status='completed'))
        self.assertFalse(should_enqueue_learning_followup(requested=False, enabled=True, flow_status='completed'))
        self.assertFalse(should_enqueue_learning_followup(requested=True, enabled=False, flow_status='completed'))
        self.assertFalse(should_enqueue_learning_followup(requested=True, enabled=True, flow_status='mapping_required_no_cms_user_created'))

    def test_full_sync_callers_disable_the_inline_grade_read(self):
        app_root = BACKEND / 'app'
        worker = (app_root / 'worker.py').read_text(encoding='utf-8')
        route = (app_root / 'api' / 'routes' / 'academic.py').read_text(encoding='utf-8')

        worker_branch = worker[worker.index("elif job.job_type == 'full_cms_sync':"):worker.index("else:\n            raise ValueError", worker.index("elif job.job_type == 'full_cms_sync':"))]
        route_branch = route[route.index('def sync_class_full_cms_flow('):route.index("@router.post('/classes/{class_id}/cms-enrollment-sync'", route.index('def sync_class_full_cms_flow('))]
        for source in (worker_branch, route_branch):
            self.assertIn('sync_learning=False', source)
            self.assertIn('_enqueue_delayed_learning_sync_followup', source)


if __name__ == '__main__':
    unittest.main()
