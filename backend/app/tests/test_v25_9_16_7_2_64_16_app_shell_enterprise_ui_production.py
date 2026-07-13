import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_version_and_database_boundary():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert 'App Shell & Enterprise UI Rebuild + Production UI Hardening' in text('README.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_shell_has_accessible_collapsible_desktop_and_mobile_navigation():
    shell = text('frontend/components/layout/AppShell.tsx')
    css = text('frontend/styles/production-ui.css')
    for token in (
        "const SIDEBAR_STORAGE_KEY = 'ai-shell-sidebar'",
        "const GROUP_STORAGE_KEY = 'ai-shell-nav-groups'",
        "const THEME_STORAGE_KEY = 'ai-shell-theme'",
        "window.matchMedia('(max-width: 767px)')",
        "event.key === 'Escape'",
        'drawer.inert = mobile && !drawerOpen',
        'menuButtonRef.current?.focus()',
        'aria-current={active ? \'page\' : undefined}',
        'data-tooltip={item.label}',
        'aria-label="Điều hướng chính"',
    ):
        assert token in shell
    assert '--shell-sidebar-collapsed-width: 64px' in css
    assert '--shell-sidebar-width: 220px' in css
    assert '--shell-topbar-height: 56px' in css
    assert "html[data-sidebar='collapsed']" in css
    assert '.enterprise-sidebar.mobile-open' in css
    assert '@media (max-width: 767px)' in css
    assert '@media (prefers-reduced-motion: reduce)' in css


def test_v64_16_uses_svg_icons_and_no_icon_font_or_unicode_navigation():
    shell = text('frontend/components/layout/AppShell.tsx')
    icons = text('frontend/components/icons/AppIcon.tsx')
    assert "from '../icons/AppIcon'" in shell
    assert '<svg' in icons and 'aria-hidden="true"' in icons
    assert 'lucide' not in shell.lower()
    for forbidden in ('font-awesome', 'material-icons', 'metronic', 'jquery', 'bootstrap'):
        assert forbidden not in shell.lower()


def test_v64_16_bootstraps_theme_and_sidebar_before_hydration_without_disabling_zoom():
    layout = text('frontend/app/layout.tsx')
    assert "localStorage.getItem('ai-shell-theme')" in layout
    assert "localStorage.getItem('ai-shell-sidebar')" in layout
    assert "d.dataset.sidebar=s==='expanded'?'expanded':'collapsed'" in layout
    assert "d.dataset.mobileNav='closed'" in layout
    assert '<html lang="vi-VN" suppressHydrationWarning>' in layout
    assert "import '../styles/production-ui.css'" in layout
    assert 'maximumScale' not in layout


def test_v64_16_production_removes_diagnostics_and_test_controls_from_navigation():
    runtime = text('frontend/lib/runtime.ts')
    shell = text('frontend/components/layout/AppShell.tsx')
    compose = text('docker-compose.prod.yml')
    dockerfile = text('frontend/Dockerfile')
    env = text('.env.production.example')
    readiness = text('frontend/app/ops/readiness/page.tsx')
    analytics = text('frontend/app/analytics/learning/page.tsx')
    settings = text('frontend/app/settings/page.tsx')
    student_class = text('frontend/app/student-management/classes/[classId]/page.tsx')
    assert "APP_ENV === 'production'" in runtime
    assert 'SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI' in runtime
    assert 'diagnostic: true' in shell
    assert '!item.diagnostic || SHOW_DIAGNOSTICS_UI' in shell
    for source in (compose, dockerfile, env):
        assert 'NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI' in source
        assert 'false' in source
    assert 'notFound()' in readiness
    assert 'ReadinessClient' not in readiness and 'getUxAcceptance' not in readiness
    assert not (ROOT / 'frontend/app/ops/readiness/ReadinessClient.tsx').exists()
    assert "@import '../styles/ops-readiness.css'" not in text('frontend/app/globals.css')
    assert 'SHOW_DIAGNOSTICS_UI && showOperations' in analytics
    assert 'SHOW_DIAGNOSTICS_UI && canRunFullCmsSync' in student_class
    for forbidden in ('Kiểm tra GPT', 'Kiểm tra Open edX', 'Bật model mô phỏng', 'Dùng Open edX mô phỏng', '<option value="demo">', 'testModelGateway', 'testOpenEdxConnection'):
        assert forbidden not in settings


def test_v64_16_production_auth_context_has_no_demo_identity_or_legacy_role_fallback():
    context = text('frontend/context/AppContext.tsx')
    assert "const IS_PRODUCTION = process.env.NEXT_PUBLIC_APP_ENV === 'production'" in context
    assert "getStoredString(STORAGE_KEYS.courseId, '')" in context
    assert "const canUseLegacyRoleFallback = !IS_PRODUCTION && !cookieAuthenticated" in context
    assert 'if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.courseId, value)' in context
    assert 'if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.userId, value)' in context
    assert "'course-v1:FPT+DBI102+su26'" not in context
    assert "'student1'" not in context


def test_v64_16_navigation_and_route_guard_use_permissions():
    shell = text('frontend/components/layout/AppShell.tsx')
    for permission in (
        'view_questions',
        'publish_questions',
        'view_training_reports',
        'view_jobs',
        'manage_training_deadlines',
        'manage_settings',
        'view_rbac',
        'view_ops_readiness',
    ):
        assert permission in shell
    assert 'availableItems.filter((item) => !item.permission || can(item.permission))' in shell
    assert 'requiredPermissionForPath' in shell
    assert 'router.replace(fallbackHref)' in shell
    assert 'routeAllowed ? children' in shell


def test_v64_16_page_header_is_shared_on_main_enterprise_pages():
    component = text('frontend/components/layout/PageHeader.tsx')
    assert 'primaryAction' in component and 'secondaryActions' in component
    routes = (
        'frontend/app/teacher-management/page.tsx',
        'frontend/app/student-management/page.tsx',
        'frontend/app/analytics/learning/page.tsx',
        'frontend/app/jobs/page.tsx',
        'frontend/app/audit/page.tsx',
        'frontend/app/ap-sync/page.tsx',
        'frontend/app/premises/page.tsx',
        'frontend/app/semesters/page.tsx',
        'frontend/app/bank/quiz/page.tsx',
        'frontend/app/settings/page.tsx',
    )
    for route in routes:
        source = text(route)
        assert 'PageHeader' in source, route


def test_v64_16_table_and_page_geometry_is_unified_and_body_does_not_scroll_horizontally():
    css = text('frontend/styles/production-ui.css')
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    for token in (
        'html, body { width: 100%; min-height: 100%; overflow-x: clip; }',
        '.enterprise-content',
        'min-width: 0',
        'overflow-x: auto !important',
        'width: 64px',
        'width: 52px',
        'min-width: max-content',
    ):
        assert token in css
    for token in ('<colgroup>', 'SELECTION_COLUMN_WIDTH = 52', "if (indexColumn) return 64", "'--sticky-offset'"):
        assert token in table


def test_v64_16_preserves_backend_business_and_data_safety_boundaries():
    assignment = text('backend/app/services/academic/assignment_external.py')
    rbac = text('backend/app/services/business_rbac.py')
    context = text('AI_SERVER_PROJECT_CONTEXT_V25_9_16_7_2_64_16.md')
    runbook = text('RUN_V25_9_16_7_2_64_16.md')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac
    assert 'Department → Subject → một Subject Version cuối/term → Chapter → Question' in context
    assert 'Không reset DB' in context
    assert 'docker compose down -v' in runbook
