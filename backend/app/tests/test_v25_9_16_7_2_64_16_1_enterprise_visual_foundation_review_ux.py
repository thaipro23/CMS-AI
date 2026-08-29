import json
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.1'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_1_version_and_database_boundary():
    package = json.loads(text('frontend/package.json'))
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_1_dark_sidebar_light_workspace_and_no_theme_switcher():
    shell = text('frontend/components/layout/AppShell.tsx')
    layout = text('frontend/app/layout.tsx')
    css = text('frontend/styles/enterprise-visual-foundation.css')
    assert "document.documentElement.dataset.theme = 'light'" in shell
    assert 'toggleTheme' not in shell
    assert 'THEME_STORAGE_KEY' not in shell
    assert 'ai-shell-theme' not in shell
    assert "d.dataset.theme='light'" in layout
    assert "import '../styles/enterprise-visual-foundation.css'" in layout
    assert '--sidebar-bg: #101827' in css
    assert '.enterprise-sidebar {' in css and 'background: var(--sidebar-bg) !important' in css
    assert '.enterprise-topbar {' in css and 'background: rgba(255, 255, 255, .97) !important' in css
    assert 'color-scheme: light' in css


def test_v64_16_1_dense_table_contract_has_kinds_priorities_and_compact_geometry():
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    css = text('frontend/styles/enterprise-visual-foundation.css')
    for token in (
        "export type EnterpriseColumnKind = 'index' | 'selection' | 'identity' | 'number' | 'status' | 'date' | 'progress' | 'actions' | 'text'",
        "export type EnterpriseColumnPriority = 'required' | 'important' | 'optional'",
        'const SELECTION_COLUMN_WIDTH = 44',
        'function inferKind',
        'function defaultWidth',
        'enterprise-priority-',
        'getRowClassName',
    ):
        assert token in table
    assert 'container-type: inline-size' in css and '@container (max-width: 1050px)' in css
    assert '.enterprise-priority-optional' in css
    assert '.enterprise-kind-number' in css
    assert 'table-layout: fixed' in css


def test_v64_16_1_question_review_is_preview_first_and_keyboard_operable():
    page = text('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    table = text('frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx')
    css = text('frontend/styles/enterprise-visual-foundation.css')
    assert 'question-review-drawer' in page
    assert 'activeQuestionId={previewQuestion?.id}' in page
    for key in ("event.key.toLowerCase() === 'j'", "event.key.toLowerCase() === 'k'", "event.key.toLowerCase() === 'a'", "event.key.toLowerCase() === 'r'", "event.key.toLowerCase() === 'e'", "event.key === 'Escape'"):
        assert key in page
    assert 'selectedQuestionCount > 0 ?' in page
    assert 'Duyệt hết câu chờ' not in page
    assert 'activeQuestionId?: string | null' in table
    assert "getRowClassName={(row) => row.id === activeQuestionId ? 'is-active-review-row' : ''}" in table
    assert 'row-action-menu' in table
    assert '.question-review-drawer' in css


def test_v64_16_1_question_table_prioritizes_question_and_reduces_row_actions():
    table = text('frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx')
    assert "key: 'question'" in table and "kind: 'identity'" in table
    assert "key: 'concept'" in table and "priority: 'optional'" in table
    assert "key: 'source'" in table and "priority: 'optional'" in table
    assert "key: 'actions'" in table and "kind: 'actions'" in table
    assert table.count('Xem') >= 1
    assert '•••' in table


def test_v64_16_1_permissions_page_is_user_first_not_role_card_wall():
    users = text('frontend/app/users/page.tsx')
    assert 'title="Người dùng & phân quyền"' in users
    assert 'permission-workspace' in users
    assert 'tableId="rbac-assignments"' in users
    assert '<EnterpriseDataTable' in users
    assert 'Quản trị toàn hệ thống' in users
    assert 'Không giới hạn phạm vi' in users
    assert 'aria-label="Gán quyền mới"' in users
    assert 'role-picker-grid' not in users
    assert 'Gán quyền nhanh' not in users


def test_v64_16_1_analytics_hides_raw_fetch_error():
    analytics = text('frontend/app/analytics/learning/page.tsx')
    assert 'function analyticsErrorMessage' in analytics
    assert 'Không kết nối được API phân tích học tập.' in analytics
    assert 'failed to fetch|networkerror|load failed|network request failed' in analytics
    assert "analyticsErrorMessage(error, 'Không tải được kết quả học online')" in analytics


def test_v64_16_1_catalog_tables_use_shared_enterprise_component_and_safe_actions():
    premises = text('frontend/app/premises/page.tsx')
    semesters = text('frontend/app/semesters/page.tsx')
    for source in (premises, semesters):
        assert '<EnterpriseDataTable' in source
        assert "kind: 'actions'" in source
        assert 'row-action-menu' in source
    assert 'formatVNDate' in semesters


def test_v64_16_1_hot_tables_define_narrow_numeric_and_optional_columns():
    for route in (
        'frontend/app/student-management/page.tsx',
        'frontend/app/teacher-management/page.tsx',
        'frontend/app/jobs/page.tsx',
        'frontend/app/audit/page.tsx',
    ):
        source = text(route)
        assert ("kind: 'number'" in source or "kind: 'index'" in source or 'kind: "number"' in source or 'kind: "index"' in source), route
        assert ("priority: 'optional'" in source or 'priority: "optional"' in source), route
        assert '<EnterpriseDataTable' in source, route


def test_v64_16_1_does_not_add_bootstrap_or_change_business_boundaries():
    package = text('frontend/package.json').lower()
    lock = text('frontend/package-lock.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assert '"bootstrap"' not in lock
    assignment = text('backend/app/services/academic/assignment_external.py')
    rbac = text('backend/app/services/business_rbac.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac


def test_v64_16_1_production_diagnostics_remain_hidden():
    runtime = text('frontend/lib/runtime.ts')
    readiness = text('frontend/app/ops/readiness/page.tsx')
    compose = text('docker-compose.prod.yml')
    assert 'SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI' in runtime
    assert 'notFound()' in readiness
    assert 'NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI' in compose and 'false' in compose
