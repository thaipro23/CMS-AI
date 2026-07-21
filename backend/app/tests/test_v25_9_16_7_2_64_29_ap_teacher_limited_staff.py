from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_connector_assigns_ap_teachers_to_limited_staff_only():
    source = read('openedx-connector-plugin/openedx_ai_connector/student_insight.py')
    teacher_block = source[source.index('        if is_teacher:'):source.index('        try:\n            enrollment = CourseEnrollment.objects.filter', source.index('        if is_teacher:'))]

    assert "('common.djangoapps.student.roles', 'CourseLimitedStaffRole')" in source
    assert 'limited_role = CourseLimitedStaffRole(course_key)' in teacher_block
    assert 'limited_role.add_users(user)' in teacher_block
    assert "'course_role': 'limited_staff'" in teacher_block
    assert "'enrollment_status': 'course_limited_staff'" in teacher_block
    assert 'CourseStaffRole(course_key)' in teacher_block
    assert 'full_staff_role.remove_users(user)' in teacher_block
    assert teacher_block.index('limited_role.add_users(user)') < teacher_block.index('full_staff_role.remove_users(user)')
    assert "'course_role': 'staff'" not in teacher_block
    assert '\n                    role.add_users(user)' not in teacher_block


def test_connector_verifies_exact_roles_and_downgrades_legacy_course_staff():
    source = read('openedx-connector-plugin/openedx_ai_connector/student_insight.py')
    assert 'def _course_role_has_exact_user(role: Any, user: Any) -> bool:' in source
    assert 'role.users_with_role().filter(pk=user_pk).exists()' in source
    assert "status_value = 'course_limited_staff_migrated'" in source
    assert "'full_course_staff_remaining': False" in source
    assert "'removed_course_staff': had_full_staff" in source


def test_backend_accepts_only_verified_limited_staff_results():
    source = read('backend/app/services/academic/sync_enrollment.py')
    assert "'already_course_limited_staff', 'course_limited_staff_added', 'course_limited_staff_migrated'" in source
    assert "result.get('verified_after_write') is True" in source
    assert "'course_role': str(result.get('course_role') or 'limited_staff')" in source
    assert 'giảng viên AP được gán Limited Staff' in source


def test_connector_version_is_bumped_for_role_policy_change():
    source = read('openedx-connector-plugin/openedx_ai_connector/student_insight.py')
    setup = read('openedx-connector-plugin/setup.py')
    assert "CONNECTOR_VERSION = '25.9.16.5.99'" in source
    assert "CONNECTOR_CONTRACT_VERSION = 'learning-sync/v25.9.16.5.99'" in source
    assert 'version="0.1.6"' in setup
