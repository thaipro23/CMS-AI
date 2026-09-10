from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / 'backend/app/services/academic/access.py'
SCOPE_ROUTE = ROOT / 'backend/app/api/routes/academic_scope.py'
API_ROUTER = ROOT / 'backend/app/api/router.py'
APP_SHELL = ROOT / 'frontend/components/layout/AppShell.tsx'


def test_campus_owner_can_open_subject_when_subject_has_class_in_owned_campus():
    source = ACCESS.read_text(encoding='utf-8')
    assert 'if decision.campus_codes:' in source
    assert 'AcademicClass.subject_id == subject_id' in source
    assert 'func.lower(AcademicClass.campus).in_(decision.campus_codes)' in source
    assert 'campus_subject_exists' in source


def test_training_scope_endpoint_resolves_branch_from_campus_catalog():
    source = SCOPE_ROUTE.read_text(encoding='utf-8')
    router_source = API_ROUTER.read_text(encoding='utf-8')
    assert "@router.get('/training-scope')" in source
    assert 'BusinessRBACService(db).accessible_campus_codes' not in source
    assert 'rbac.accessible_campus_codes(user)' in source
    assert 'AcademicCampus.campus_code' in source
    assert "'preferred_branch': preferred_branch" in source
    assert "'preferred_campus': preferred_campus" in source
    assert 'academic_scope.router' in router_source


def test_app_shell_uses_business_role_and_training_scope_instead_of_legacy_viewer_only():
    source = APP_SHELL.read_text(encoding='utf-8')
    assert "CAMPUS_OWNER: 'Chủ cơ sở'" in source
    assert 'businessRoleLabel(assignments, ROLE_LABELS[role])' in source
    assert 'effectiveRoleLabel' in source
    assert "`${API}/academic/training-scope`" in source
    assert "params.delete('term_id')" in source
    assert "params.delete('block_id')" in source
