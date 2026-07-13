import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.15'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_15_version_package_and_database_boundary():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Scoped RBAC + Analytics Workspace Stabilization + Unified Table Contract' in text('README.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_15_uses_existing_academic_class_scope_index_without_duplicate_migration():
    model = text('backend/app/models/academic.py')
    assert "Index('ix_academic_classes_scope_lookup', 'branch', 'campus', 'term_id', 'block_id', 'subject_id', 'class_code', 'active')" in model
    assert 'Mirrors migration 0050' in model
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))


def test_v64_15_analytics_workspace_replaces_eager_parallel_result_requests():
    route = text('backend/app/api/routes/learning_analytics.py')
    api = text('frontend/lib/api.ts')
    page = text('frontend/app/analytics/learning/page.tsx')
    assert "@router.get('/classes/{class_id}/workspace')" in route
    assert 'class_behavior_workspace' in route
    assert "'summary': service.behavior_summary" in route
    assert "'rows': service.behavior_rows" in route
    assert "'doctor': service.class_result_doctor" in route
    assert 'getAnalyticsClassWorkspace' in api
    assert 'getAnalyticsClassWorkspace' in page
    assert 'getAnalyticsClassBehaviorSummary' not in page
    assert 'listAnalyticsClassBehavior' not in page


def test_v64_15_operations_are_permission_gated_and_not_loaded_by_default():
    route = text('backend/app/api/routes/learning_analytics.py')
    page = text('frontend/app/analytics/learning/page.tsx')
    app_shell = text('frontend/components/layout/AppShell.tsx')
    assert "require_permission('view_ops_readiness')" in route
    assert 'const [showOperations, setShowOperations] = useState(false)' in page
    assert "if (!showOperations || !can('view_ops_readiness'))" in page
    assert "showOperations && can('view_ops_readiness')" in page
    assert 'Mở kiểm tra vận hành' in page
    assert "permission: 'view_ops_readiness'" in app_shell
    assert "permission: 'view_training_reports'" in app_shell


def test_v64_15_teacher_analytics_is_view_only_and_recalculate_stays_privileged():
    route = text('backend/app/api/routes/learning_analytics.py')
    rbac = text('backend/app/services/business_rbac.py')
    access = text('backend/app/services/academic/access.py')
    assert "require_permission('manage_training_deadlines')" in route
    assert '_has_ap_teacher_assignment' in rbac
    assert 'ROLE_PERMISSIONS[TEACHER_ASSIGNED]' in rbac
    assert 'AcademicTeacher.username' in access and 'AcademicTeacher.email' in access


def test_v64_15_identity_reconciliation_ui_and_requests_are_removed():
    page = text('frontend/app/student-management/classes/[classId]/page.tsx')
    assert 'Kiểm tra identity CMS/RollNumber' not in page
    assert 'getAcademicClassIdentityReconciliation' not in page
    assert 'cleanupAcademicClassIdentityReconciliation' not in page
    assert 'RollNumber identity' not in page
    # Compatibility backend remains until a separately reviewed API removal.
    assert 'identity_reconciliation_for_class' in text('backend/app/services/academic/identity.py')


def test_v64_15_enterprise_table_has_one_geometry_contract():
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    css = text('frontend/styles/enterprise-ui.css')
    for token in ('columnLayouts', '<colgroup>', 'SELECTION_COLUMN_WIDTH = 52', "if (indexColumn) return 64", "'--sticky-offset'"):
        assert token in table
    assert 'stickyOffset?: number' in table
    assert 'Sticky offsets are calculated from visible column widths' in table
    assert '.enterprise-index-column' in css
    assert 'width: 64px' in css
    assert 'overflow-x: auto' in css


def test_v64_15_rbac_has_hierarchy_permissions_and_dynamic_ap_teacher_access():
    rbac = text('backend/app/services/business_rbac.py')
    schema = text('backend/app/schemas/rbac.py')
    route = text('backend/app/api/routes/rbac.py')
    context = text('frontend/context/AppContext.tsx')
    for token in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert token in rbac
    assert "'department.update'" in rbac
    assert "'ops.readiness.view'" in rbac
    assert "'rbac.view'" in rbac
    assert '_has_ap_teacher_assignment' in rbac
    assert 'permission_codes' in schema and 'business_permissions' in schema
    assert 'business_permissions' in route and 'is_system_admin' in route
    assert "require_permission('view_rbac')" in route
    assert "require_permission('view_questions')" not in route
    assert 'canScope' in context and 'assignment.permission_codes' in context


def test_v64_15_bank_and_rbac_actions_are_scope_aware():
    department = text('frontend/app/bank/_components/pages/DepartmentsPage.tsx')
    subjects = text('frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx')
    versions = text('frontend/app/bank/_components/pages/SubjectVersionsPage.tsx')
    chapters = text('frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx')
    questions = text('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    users = text('frontend/app/users/page.tsx')
    bank_route = text('backend/app/api/routes/question_bank_v2.py')
    assert "canScope('manage_department'" in department
    assert "canScope('subject.create'" in subjects
    assert "canScope('subject.update'" in versions
    assert "canScope('subject.update'" in chapters
    for token in ('canGenerateQuestions', 'canEditQuestions', 'canReviewQuestions', 'canPublishQuestions'):
        assert token in questions
    assert 'grantableRoleCodes' in users
    assert "businessPermissions.includes('subject.assign_owner')" in users
    assert "businessPermissions.includes('reviewer.assign')" in users
    assert "_require_business(db, user, 'department.update', 'DEPARTMENT', department_id)" in bank_route


def test_v64_15_preserves_bank_assignment_and_data_safety_boundaries():
    assignment = text('backend/app/services/academic/assignment_external.py')
    context = text('AI_SERVER_PROJECT_CONTEXT_V25_9_16_7_2_64_15.md')
    runbook = text('RUN_V25_9_16_7_2_64_15.md')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    assert 'Department → Subject → một final Subject Version/term → Chapter → Question' in context
    assert 'Không reset DB/xóa volume/sửa tay `alembic_version`' in context
    assert 'Không dùng `docker compose down -v`' in runbook


def test_v64_15_runtime_static_gates_receive_bounded_source_snapshot():
    dockerfile = text('backend/Dockerfile.prod')
    compose = text('docker-compose.prod.yml')
    ux = text('backend/app/services/ux_acceptance.py')
    security = text('backend/app/services/security_attack_simulation.py')
    maintainability = text('backend/app/services/maintainability_contract.py')
    assert 'SOURCE_CONTRACT_ROOT=/source-contract' in dockerfile
    assert 'COPY frontend/app/ /source-contract/frontend/app/' in dockerfile
    assert 'COPY openedx-connector-plugin/ /source-contract/openedx-connector-plugin/' in dockerfile
    assert 'dockerfile: backend/Dockerfile.prod' in compose
    for source in (ux, security, maintainability):
        assert "os.getenv('SOURCE_CONTRACT_ROOT')" in source
