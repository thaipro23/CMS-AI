from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Auth/RBAC Security Boundary Hardening'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v48_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v48_business_rbac_has_campus_scope_guards():
    service = read('backend/app/services/business_rbac.py')
    assert 'def normalize_campus_code(' in service
    assert 'def campus_scope_for_user(' in service
    assert 'def can_access_campus(' in service
    assert 'def require_campus_access(' in service
    assert 'def ensure_requested_campus_filter_allowed(' in service
    assert 'def can_access_academic_scope(' in service
    assert 'def require_academic_scope(' in service
    assert 'Scope cơ sở giới hạn phải chọn một cơ sở cụ thể' in service
    assert 'Jobs created after v25.9.16.7.2.64.12' in service


def test_v48_academic_jobs_are_scope_guarded_and_auditable():
    route = read('backend/app/api/routes/academic.py')
    assert 'ensure_requested_campus_filter_allowed(' in route
    assert "require_filter_when_scoped=True" in route
    assert "'approved_campus_codes'" in route
    assert "'approved_branch'" in route
    assert "'scope_enforced_by_backend': True" in route
    assert 'can_access_academic_scope(user, campus=job.campus' in route
    assert 'require_academic_scope(user, campus=job.campus' in route
    assert 'tải file báo cáo giáo viên' in route
    assert 'xem job xử lý hàng loạt' in route


def test_v48_rbac_scope_audit_endpoint_exists():
    route = read('backend/app/api/routes/rbac.py')
    assert "@router.get('/scope-audit')" in route
    assert 'campus_scope_for_user(user)' in route
    assert 'AcademicService(db).access_decision(user)' in route
    assert 'visibility_for_user(user)' in route
    assert "'backend_enforced': True" in route
    assert "'academic_scope'" in route
    assert "'bank_scope'" in route


def test_v48_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
