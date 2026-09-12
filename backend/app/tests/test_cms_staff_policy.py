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
            validate_cms_provisioning(
                {'exists': True, 'user_profile_ok': True, 'is_staff': False},
                require_staff=True,
            )

        verified = validate_cms_provisioning(
            {'exists': True, 'user_profile_ok': True, 'is_staff': True, 'is_superuser': False},
            require_staff=True,
        )
        self.assertTrue(verified['is_staff'])
        self.assertFalse(verified['is_superuser'])


if __name__ == '__main__':
    unittest.main()
