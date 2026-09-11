from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class RBACIdentityLoginSyncContractTests(unittest.TestCase):
    def test_email_identity_normalizes_and_derives_username(self):
        from app.services.identity import normalize_email_identity

        self.assertEqual(
            normalize_email_identity('  Nguyen.Van.A@FPT.EDU.VN '),
            {'email': 'nguyen.van.a@fpt.edu.vn', 'username': 'nguyen.van.a'},
        )

    def test_invalid_email_is_rejected(self):
        from app.services.identity import normalize_email_identity

        with self.assertRaises(ValueError):
            normalize_email_identity('not-an-email')

    def test_rbac_service_provisions_connector_with_staff_profile_payload(self):
        source = (BACKEND / 'app/services/business_rbac.py').read_text(encoding='utf-8')
        self.assertIn('create_missing=True', source)
        self.assertIn("'person_type': 'teacher'", source)
        self.assertIn("'email': email", source)

    def test_login_profile_model_and_exchange_are_wired(self):
        model = (BACKEND / 'app/models/identity.py').read_text(encoding='utf-8')
        auth = (BACKEND / 'app/api/routes/auth.py').read_text(encoding='utf-8')
        self.assertIn("__tablename__ = 'ai_user_profiles'", model)
        self.assertIn('last_login_at', model)
        self.assertIn('upsert_login', auth)

    def test_connector_enforces_unusable_password_and_profile(self):
        for relative in (
            'openedx-connector-plugin/openedx_ai_connector/student_insight.py',
        ):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn("return 'unusable', '', 'enforced_no_local_password'", source)
            self.assertIn('_ensure_user_profile', source)
            self.assertIn('set_unusable_password()', source)

    def test_rbac_output_and_frontend_render_last_login_once(self):
        schema = (BACKEND / 'app/schemas/rbac.py').read_text(encoding='utf-8')
        service = (BACKEND / 'app/services/business_rbac.py').read_text(encoding='utf-8')
        page = (ROOT / 'frontend/app/users/page.tsx').read_text(encoding='utf-8')
        self.assertIn('last_login_at', schema)
        self.assertIn('last_login_at', service)
        self.assertIn('last_login_at', page)
        self.assertIn('Đăng nhập lần cuối', page)

    def test_score_sync_schedule_is_0500_vietnam_and_fanout_is_registered(self):
        worker = (BACKEND / 'app/worker.py').read_text(encoding='utf-8')
        self.assertIn("timezone='Asia/Ho_Chi_Minh'", worker)
        self.assertIn("'academic-score-sync-all-students'", worker)
        self.assertIn("crontab(hour=5, minute=0)", worker)
        self.assertIn("academic_sync_all_student_scores_task", worker)


if __name__ == '__main__':
    unittest.main()
