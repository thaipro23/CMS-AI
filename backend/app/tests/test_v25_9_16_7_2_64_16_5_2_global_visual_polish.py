import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.2'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_and_database_boundary():
    package = json.loads(read('frontend/package.json'))
    lock = json.loads(read('frontend/package-lock.json'))
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert lock['version'] == VERSION
    assert lock['packages']['']['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_global_visual_stylesheet_is_loaded_last():
    layout = read('frontend/app/layout.tsx')
    assert "import '../styles/global-visual-polish.css'" in layout
    assert layout.rfind('global-visual-polish.css') > layout.rfind('production-ux-browser-hotfix.css')
    css = read('frontend/styles/global-visual-polish.css')
    for token in ('--visual-card-radius', '.visual-icon', '.visual-section-card', '.enterprise-page-header-leading', '.enterprise-table-shell', '.academic-inline-notice'):
        assert token in css


def test_page_headers_kpis_sections_and_notices_use_svg_icons():
    header = read('frontend/components/layout/PageHeader.tsx')
    visual = read('frontend/components/ui/VisualIcon.tsx')
    training = read('frontend/components/training/TrainingWorkspace.tsx')
    operations = read('frontend/components/operations/OperationsWorkspace.tsx')
    notices = read('frontend/components/ui/InlineNotice.tsx') + read('frontend/components/ui/ActionMessage.tsx')
    assert '<VisualIcon' in header
    assert 'inferVisualMeta' in visual
    assert '<VisualIcon' in training
    assert '<VisualIcon' in operations
    assert notices.count('<VisualIcon') >= 2


def test_table_keeps_full_content_and_has_visual_summary():
    table = read('frontend/components/table/EnterpriseDataTable.tsx')
    css = read('frontend/styles/global-visual-polish.css')
    assert 'data-column-contract="full-content"' in table
    assert 'responsiveHiddenColumns' not in table
    assert 'enterprise-table-summary-icon' in table
    assert 'overflow-wrap: anywhere' in css
    assert '.enterprise-data-table tbody tr:hover td' in css


def test_all_production_domains_receive_shared_visual_contract():
    css = read('frontend/styles/global-visual-polish.css')
    for token in (
        '.dashboard-kpi-card', '.bank-multipage', '.question-review-panel', '.quiz-workflow-step',
        '.training-kpi', '.online-learning-summary-strip', '.operations-kpi', '.ap-sync-summary',
        '.workspace-tabs', '.rbac-user-summary', '.pricing-summary', '.term-block-summary',
    ):
        assert token in css
    active_pages = [path for path in (ROOT / 'frontend/app').rglob('page.tsx') if 'ops/readiness' not in path.as_posix()]
    assert len(active_pages) >= 25


def test_semantic_status_uses_svg_not_unicode_markers():
    badge = read('frontend/components/ui/StatusBadge.tsx')
    workflow = read('frontend/components/training/TrainingWorkspace.tsx')
    assert '<AppIcon' in badge
    assert "success: 'check'" in badge
    assert "<AppIcon name=\"check\"" in workflow
    assert "completed ? '✓'" not in workflow


def test_no_bootstrap_jquery_or_business_contract_change():
    package = read('frontend/package.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assert 'jquery' not in package
    assignment = read('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    migrations = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert migrations[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'


def test_visual_source_report_exists_and_is_read_only():
    script = read('scripts/global-visual-polish-report.sh')
    assert 'global-visual-polish.json' in script
    assert 'no_bootstrap_or_jquery' in script
    for forbidden in ('enqueue', 'INSERT INTO', 'DELETE FROM', 'docker compose down -v'):
        assert forbidden not in script
