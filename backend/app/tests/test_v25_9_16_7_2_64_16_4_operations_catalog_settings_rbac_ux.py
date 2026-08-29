import json
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.4'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_4_version_and_database_boundary():
    package = json.loads(text('frontend/package.json'))
    lock = json.loads(text('frontend/package-lock.json'))
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert lock['version'] == VERSION
    assert lock['packages']['']['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'APP_VERSION={VERSION}' in text('.env.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_4_shared_operations_workspace_contract_is_loaded():
    component = text('frontend/components/operations/OperationsWorkspace.tsx')
    css = text('frontend/styles/operations-catalog-rbac-ux.css')
    layout = text('frontend/app/layout.tsx')
    for token in ('OperationsKpiStrip', 'CompactFilterBar', 'WorkspaceTabs', 'WorkspaceSection', 'SideDrawer', 'InfoPairGrid'):
        assert token in component
    assert "import '../styles/operations-catalog-rbac-ux.css'" in layout
    for token in ('.operations-kpi-strip', '.operations-filter-bar', '.workspace-tabs', '.side-drawer', '.rbac-user-workspace', '.ap-sync-workspace'):
        assert token in css


def test_v64_16_4_jobs_and_audit_use_compact_workspaces_and_detail_drawers():
    jobs = text('frontend/app/jobs/page.tsx')
    audit = text('frontend/app/audit/page.tsx')
    for source in (jobs, audit):
        assert '<OperationsKpiStrip' in source
        assert '<CompactFilterBar' in source
        assert '<SideDrawer' in source
        assert '<InfoPairGrid' in source
    assert 'tableId="ops-jobs-v2"' in jobs
    assert 'tableId="ops-recent-quizzes"' in jobs
    assert 'tableId="ops-audit-v2"' in audit
    assert '<Popup' not in jobs


def test_v64_16_4_ap_sync_is_plan_progress_result_workspace():
    page = text('frontend/app/ap-sync/page.tsx')
    assert '<OperationsKpiStrip' in page
    assert 'Kế hoạch đồng bộ' in page
    assert 'Tiến trình & kết quả' in page
    assert 'ap-sync-workspace' in page
    assert 'Kiểm tra kế hoạch' in page
    assert '<table' not in page
    assert 'enqueueAcademicApSyncJob' in page


def test_v64_16_4_catalog_pages_use_enterprise_tables_and_compact_actions():
    premises = text('frontend/app/premises/page.tsx')
    semesters = text('frontend/app/semesters/page.tsx')
    assert 'tableId="premises-v2"' in premises
    assert '<CompactFilterBar' in premises
    assert '<OperationsKpiStrip' in premises
    assert 'tableId="semesters-v2"' in semesters
    assert "key: 'blocks'" in semesters
    assert 'Lịch 2 block' in semesters
    assert 'term-block-editor' in semesters
    assert '<EnterpriseDataTable' in premises and '<EnterpriseDataTable' in semesters


def test_v64_16_4_settings_are_grouped_by_domain_tabs():
    page = text('frontend/app/settings/page.tsx')
    assert '<WorkspaceTabs' in page
    for token in ('Giới hạn tạo câu hỏi', 'Mô hình & worker', 'Kết nối Open edX', 'SSO & xác thực', 'Chi phí & pricing'):
        assert token in page
    assert 'settings-workspace' in page
    assert page.count('<WorkspaceSection') >= 6
    assert 'API key, OAuth secret, JWT secret và token' in page


def test_v64_16_4_rbac_is_user_first_scope_first():
    page = text('frontend/app/users/page.tsx')
    assert 'type UserAccessRow' in page
    assert 'tableId="rbac-users"' in page
    assert 'Người dùng đã được cấp quyền' in page
    assert 'Quyền mới' in page
    assert '<SideDrawer' in page
    assert 'Quyền trực tiếp đang được lưu; quyền kế thừa được backend áp dụng theo cây scope.' in page
    assert 'SYSTEM_ADMIN' in page and 'DEPARTMENT_HEAD' in page and 'CAMPUS_OWNER' in page
    assert 'allowedScopesByRole' in page


def test_v64_16_4_status_badge_supports_explicit_business_labels():
    badge = text('frontend/components/ui/StatusBadge.tsx')
    assert 'label?: ReactNode' in badge
    assert "active: 'Đang hiệu lực'" in badge
    assert "revoked: 'Đã thu hồi'" in badge
    assert 'label ?? LABELS[normalized]' in badge


def test_v64_16_4_keeps_business_and_production_boundaries():
    package = text('frontend/package.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assignment = text('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    rbac = text('backend/app/services/business_rbac.py')
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac
    runtime = text('frontend/lib/runtime.ts')
    assert 'SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI' in runtime
