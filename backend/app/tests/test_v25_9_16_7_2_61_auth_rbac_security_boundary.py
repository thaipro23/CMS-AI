from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v61_version_and_docs_synced():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert text('CHANGELOG.md').startswith(f'## v{VERSION} — Question Bank Quiz Creation/Auto-map Workflow Split')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert 'RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md' in '\n'.join(p.name for p in (ROOT / 'docs').glob('*64*'))


def test_v61_only_openedx_superuser_becomes_ai_admin():
    security = text('backend/app/core/security.py')
    auth = text('backend/app/api/routes/auth.py')
    studio = text('openedx-connector-plugin/openedx_ai_connector/studio.py')
    business = text('backend/app/services/business_rbac.py')
    assert "role == 'admin'" in security
    assert 'is_superuser' in security and 'is_super_admin' in security
    assert "base_role = 'admin' if is_super_admin else 'viewer'" in auth
    assert "'ai_system_admin': bool(is_super_admin)" in auth
    assert "if is_superuser:" in studio
    assert "if is_superuser or _user_in_ai_admin_group(user)" not in studio
    assert 'AI_CONNECTOR_ALLOW_ADMIN_GROUP' in studio
    assert 'Open edX bridge tokens are intentionally governed by edX superuser only' in business


def test_v61_student_ops_and_quiz_bank_roles_are_split():
    business = text('backend/app/services/business_rbac.py')
    assert "CAMPUS_OWNER = 'CAMPUS_OWNER'" in business
    assert "TEACHER_ASSIGNED = 'TEACHER_ASSIGNED'" in business
    assert "CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'academic.manage_assignment_scores', 'view_training_reports'}" in business
    assert "TEACHER_ASSIGNED: {'academic.view', 'view_training_reports'}" in business
    assert "DEPARTMENT_HEAD: 'viewer'" in business
    assert "SUBJECT_OWNER: 'viewer'" in business
    assert "CAMPUS_OWNER: 'viewer'" in business
    assert "CAMPUS_MANAGER: 'viewer'" in business
    assert "TEACHER_ASSIGNED: 'viewer'" in business


def test_v61_academic_routes_no_longer_trust_bank_permissions():
    academic_route = text('backend/app/api/routes/academic.py')
    academic_service = text('backend/app/services/academic_service.py')
    assert 'Bank permissions\n    such as course.sync no longer authorize AP/CMS class/enrollment mutations' in academic_route
    assert "'sync_course' in user.permissions" not in academic_route.split('def _require_academic_sync_permission', 1)[1].split('def _require_academic_view_permission', 1)[0]
    assert "{'view_questions', 'manage_settings'}" not in academic_route
    assert 'Bank roles\n        # (DEPARTMENT_HEAD/SUBJECT_OWNER/QUESTION_REVIEWER) no longer grant' in academic_service
    subject_block = academic_service.split('def access_decision', 1)[1].split('def assert_can_access_class', 1)[0]
    assert 'visible_subject_ids = self.rbac.accessible_subject_ids(user)' not in subject_block


def test_v61_rbac_catalog_and_frontend_support_new_roles():
    schema = text('backend/app/schemas/rbac.py')
    users = text('frontend/app/users/page.tsx')
    types = text('frontend/types/index.ts')
    assert 'CAMPUS_OWNER' in schema and 'TEACHER_ASSIGNED' in schema
    assert "'CLASS'" in schema
    assert 'CAMPUS_OWNER' in users and 'TEACHER_ASSIGNED' in users
    assert 'Giáo viên được phân công AP' in users
    assert "'CAMPUS_OWNER'" in types and "'TEACHER_ASSIGNED'" in types and "'CLASS'" in types


def test_v61_unit_reset_connector_write_is_hmac_only_and_postmessage_origin_locked():
    views = text('openedx-unit-reset-plugin/openedx_unit_reset/views.py')
    mfe = text('frontend-app-learning-patch/src/courseware/course/sequence/unit-reset/UnitResetButton.jsx')
    assert 'def _connector_hmac_only' in views
    assert 'staff cookie không được chấp nhận' in views
    upsert = views.split('def quiz_timer_config_upsert', 1)[1].split('@require_GET', 1)[0]
    assert '_connector_hmac_only(request)' in upsert
    assert '_staff_or_hmac' not in views
    assert "postMessage(message, '*')" not in mfe
    assert 'targetOriginForFrame(frame)' in mfe
    assert 'aiAllowedOrigin(event.origin)' in views
    assert "}, '*');" not in views.split('def quiz_session_runtime_js', 1)[1]


def test_v61_production_cors_no_demo_headers():
    main = text('backend/app/main.py')
    assert '_base_cors_headers' in main
    assert "if (settings.app_env or '').lower() not in {'prod', 'production'} and settings.allow_demo_role_header" in main
    cors_block = main.split('app.add_middleware(', 1)[1].split('@app.middleware', 1)[0]
    assert "allow_headers=_base_cors_headers" in cors_block
