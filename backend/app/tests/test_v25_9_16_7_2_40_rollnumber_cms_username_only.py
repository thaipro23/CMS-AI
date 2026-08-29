from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v40_version_docs_and_no_external_auth_bridge_scope_creep():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"# v{VERSION} — {TITLE}" in read('RUN_CURRENT.md')
    assert f"# v{VERSION} — {TITLE}" in read('RUN_V25_9_16_7_2_53.md')
    auth = read('backend/app/api/routes/auth.py')
    assert 'external-identity' not in auth
    assert 'EXTERNAL_IDENTITY_BRIDGE' not in read('backend/app/core/config.py')
    frontend_text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'frontend').rglob('*.tsx'))
    assert 'NEXT_PUBLIC_FEID_LOGIN_URL' not in frontend_text
    assert not (ROOT / 'frontend/app/auth/external-callback/page.tsx').exists()


def test_v40_academic_service_uses_rollnumber_student_code_as_cms_username():
    source = read('backend/app/services/academic_service.py')
    assert 'def _student_cms_username(self, student: AcademicStudent) -> str:' in source
    assert "roll_number = str(student.student_code or '').strip()" in source
    assert 'return normalize_username(roll_number)' in source
    assert "'username': cms_username" in source
    assert "'openedx_username': cms_username" in source
    assert "'ap_username': ap_username" in source
    assert "'identity_source': 'rollnumber' if student.student_code else 'ap_username_fallback'" in source
    assert 'Students: RollNumber/student_code is the canonical CMS/Open edX username.' in source
    assert "'note': 'Open edX plugin không trả user cho RollNumber/student_code này'" in source


def test_v40_student_payload_reused_for_resolve_enrollment_and_learning_sync():
    source = read('backend/app/services/academic_service.py')
    assert 'payload = [self._student_cms_payload(student, create_missing=create_missing) for student, _mapping in chunk]' in source
    assert 'payload.append(self._student_cms_payload(\n                    student,\n                    create_missing=create_missing,' in source
    assert 'payload.append(self._student_cms_payload(\n                    student,\n                    create_missing=False,' in source
    assert "item.get('username') or item.get('openedx_username') or item.get('ap_username')" in source


def test_v40_openedx_connector_preserves_ap_username_but_matches_canonical_username():
    source = read('openedx-connector-plugin/openedx_ai_connector/student_insight.py')
    assert 'def _student_payload_ap_username(item: Any) -> str:' in source
    assert "'ap_username': _student_payload_ap_username(item)" in source
    assert "is_student_rollnumber = (item.get('person_type') or 'student') == 'student' and bool(student_code) and username == _normalize_username_input(student_code)" in source
    assert "match_method = 'exact_rollnumber_username' if is_student_rollnumber else 'exact_username'" in source
    assert "'match_method': 'created_from_rollnumber' if created and is_student_rollnumber else ('created_from_ap' if created else match_method)" in source
    assert 'Đã tạo mới user CMS/Open edX từ RollNumber/student_code' in source


def test_v40_changelog_documents_scope_correction_and_no_migration():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith(f'## v{VERSION} — {TITLE}')
    first_block = changelog.split('## v25.9.16.7.2.38', 1)[0]
    assert 'Corrects the over-scoped `.39` direction' in first_block
    assert 'no FEID/Google login bridge' in first_block
    assert 'PH59017` -> `ph59017' in first_block
    assert '- No migration.' in first_block
