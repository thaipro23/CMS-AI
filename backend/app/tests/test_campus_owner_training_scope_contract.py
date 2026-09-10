from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / 'backend/app/services/academic/access.py'
SCOPE_ROUTE = ROOT / 'backend/app/api/routes/academic_scope.py'
API_ROUTER = ROOT / 'backend/app/api/router.py'
APP_SHELL = ROOT / 'frontend/components/layout/AppShell.tsx'
ACADEMIC_TABLE_STATE = ROOT / 'frontend/hooks/useAcademicTableState.ts'
STUDENT_PLATFORM_PAGE = ROOT / 'frontend/app/student-management/StudentManagementPlatformPage.tsx'
SUBJECT_CLASSES_PAGE = ROOT / 'frontend/app/student-management/subjects/[subjectId]/classes/page.tsx'


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


def test_app_shell_uses_business_role_and_normalizes_training_url_scope():
    source = APP_SHELL.read_text(encoding='utf-8')
    assert "CAMPUS_OWNER: 'Chủ cơ sở'" in source
    assert 'businessRoleLabel(assignments, ROLE_LABELS[role])' in source
    assert 'effectiveRoleLabel' in source
    assert "`${API}/academic/training-scope`" in source
    assert "params.delete('term_id')" in source
    assert "params.delete('block_id')" in source


def test_academic_table_state_keeps_scoped_owner_on_allowed_branch_and_campus():
    source = ACADEMIC_TABLE_STATE.read_text(encoding='utf-8')
    assert 'function applyTrainingScope' in source
    assert "`${API}/academic/training-scope`" in source
    assert 'branches.includes(nextBranch)' in source
    assert 'campusCodes.has(nextCampus)' in source
    assert 'merged = { ...merged, ...scoped }' in source
    assert 'trainingScopeReady' in source
    assert 'scopeReady: authReady && isAuthenticated && trainingScopeReady' in source


def test_student_operations_wait_for_scope_before_data_requests():
    platform_source = STUDENT_PLATFORM_PAGE.read_text(encoding='utf-8')
    classes_source = SUBJECT_CLASSES_PAGE.read_text(encoding='utf-8')
    assert 'state, update, scopeReady' in platform_source
    assert 'if (!scopeReady)' in platform_source
    assert 'loading={!scopeReady || loading}' in platform_source
    assert 'state, update, scopeReady' in classes_source
    assert 'if (!scopeReady)' in classes_source
    assert 'loading={!scopeReady || loading}' in classes_source
