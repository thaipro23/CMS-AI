import json
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_5_version_and_database_boundary():
    package = json.loads(text('frontend/package.json'))
    lock = json.loads(text('frontend/package-lock.json'))
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert lock['version'] == VERSION
    assert lock['packages']['']['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_5_table_uses_container_responsive_contract_without_losing_data():
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    for token in (
        "type ResponsiveTableMode = 'desktop' | 'tablet' | 'mobile'",
        'ResizeObserver',
        "window.addEventListener('resize', update)",
        'responsiveHiddenColumns',
        'enterprise-responsive-details-row',
        'aria-controls={detailsId}',
        'data-responsive-mode={responsiveMode}',
    ):
        assert token in table
    assert "if (responsiveMode === 'mobile') return priority === 'required'" in table
    assert "if (responsiveMode === 'tablet') return priority !== 'optional'" in table


def test_v64_16_5_table_selection_and_pagination_are_accessible():
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    pagination = text('frontend/components/ui/PaginationControls.tsx')
    assert 'headerCheckboxRef.current.indeterminate = somePageSelected' in table
    assert 'role="region"' in table
    assert 'scope="col"' in table
    assert 'aria-live="polite"' in table
    assert '<nav className="pagination-bar" aria-label="Phân trang dữ liệu">' in pagination
    assert "aria-current={item === currentPage ? 'page' : undefined}" in pagination
    assert 'aria-label="Số bản ghi mỗi trang"' in pagination
    assert pagination.count('type="button"') >= 5


def test_v64_16_5_shell_has_safari_and_keyboard_fallbacks():
    shell = text('frontend/components/layout/AppShell.tsx')
    assert 'media.addListener(updateMobile)' in shell
    assert 'media.removeListener(updateMobile)' in shell
    assert "drawer.toggleAttribute('inert', shouldDisable)" in shell
    assert "control.setAttribute('tabindex', '-1')" in shell
    assert 'role={mobile ? \'dialog\' : undefined}' in shell
    assert 'aria-modal={mobile && drawerOpen ? true : undefined}' in shell
    assert 'userMenuRef' in shell and "document.addEventListener('pointerdown', close)" in shell
    assert 'role="status" aria-live="polite"' in shell


def test_v64_16_5_drawers_lock_scroll_and_expose_descriptions():
    workspace = text('frontend/components/operations/OperationsWorkspace.tsx')
    assert "document.body.style.overflow = 'hidden'" in workspace
    assert 'document.body.style.overflow = previousOverflow' in workspace
    assert 'aria-describedby={description ? descriptionId : undefined}' in workspace
    assert '<p id={descriptionId}>{description}</p>' in workspace
    assert 'aria-label={`Đóng ${title}`}' in workspace


def test_v64_16_5_final_css_covers_mobile_safe_area_forced_colors_and_motion():
    css = text('frontend/styles/production-ux-acceptance.css')
    layout = text('frontend/app/layout.tsx')
    assert "import '../styles/production-ux-acceptance.css'" in layout
    for token in (
        'min-width: 320px',
        'env(safe-area-inset-bottom)',
        '@media (forced-colors: active)',
        '@media (hover: none) and (pointer: coarse)',
        '@media (prefers-reduced-motion: reduce)',
        ".enterprise-table-shell[data-responsive-mode='mobile']",
        '.enterprise-responsive-details-row',
    ):
        assert token in css


def test_v64_16_5_keeps_production_and_business_boundaries():
    package = text('frontend/package.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assert 'jquery' not in package
    assignment = text('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    runtime = text('frontend/lib/runtime.ts')
    assert 'SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI' in runtime
    rbac = text('backend/app/services/business_rbac.py')
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac
