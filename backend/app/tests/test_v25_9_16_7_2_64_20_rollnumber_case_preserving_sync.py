from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_ai_server_preserves_rollnumber_and_blocks_ap_username_fallback():
    source = read('backend/app/services/academic/sync_enrollment.py')
    assert "return str(student.student_code or '').strip()" in source
    assert 'return self._student_rollnumber(student)' in source
    assert "'identity_source': 'rollnumber'" in source
    assert "'match_status': 'missing_student_code'" in source
    assert 'Thiếu RollNumber/student_code nên không tạo user CMS/Open edX và không enroll' in source
    assert "by_username.get(normalize_username(student.username))" not in source
    assert "return normalize_username(student.username)" not in source


def test_connector_lookup_is_case_insensitive_but_student_create_preserves_case():
    source = read('openedx-connector-plugin/openedx_ai_connector/student_insight.py')
    assert 'def _preserve_username_input(value: Any) -> str:' in source
    assert "username = _clean_user_token(username, preserve_case=is_student)" in source
    assert "User.objects.filter(username__iexact=username).first()" in source
    assert "_normalize_username_input(username) == _normalize_username_input(student_code)" in source
    assert "'status': 'skipped_missing_rollnumber'" in source
    assert "item.get('roll_number')" in source


def test_mapping_confidence_and_stale_state_follow_rollnumber_contract():
    helpers = read('backend/app/services/academic/helpers.py')
    service = read('backend/app/services/academic_service.py')
    identity = read('backend/app/services/academic/identity.py')
    assert "'exact_rollnumber_username'" in helpers
    assert "'created_from_rollnumber'" in helpers
    assert "status_value in {'missing', 'missing_student_code', 'manual_required'}" in service
    assert 'canonical_lookup = normalize_username(canonical_username)' in identity
    assert "openedx_username or self._student_cms_username(student) or None" in identity
