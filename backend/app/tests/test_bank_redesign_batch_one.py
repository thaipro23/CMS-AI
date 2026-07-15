from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_app_shell_has_exact_bank_navigation_and_shared_tablet_drawer_breakpoint():
    shell = read('frontend/components/layout/AppShell.tsx')
    assert "const SHELL_MOBILE_QUERY = '(max-width: 1023px)'" in shell
    assert "href: '/bank', label: 'Tổng quan'" in shell
    assert "href: '/bank/departments'" in shell
    assert "label: 'Ngân hàng đề'" in shell
    assert "exact: true" in shell
    assert 'function navMatchScore' in shell
    assert 'function bestNavItem' in shell
    assert 'enterprise-nav-link active' not in shell  # active class remains state-driven


def test_app_provider_first_render_is_deterministic_before_browser_hydration():
    context = read('frontend/context/AppContext.tsx')
    assert 'const [clientReady, setClientReady] = useState(false)' in context
    assert "const [courseId, setCourseIdState] = useState('')" in context
    assert 'setClientReady(true)' in context
    assert 'if (!clientReady)' in context


def test_departments_page_uses_shared_enterprise_patterns_and_explicit_states():
    page = read('frontend/app/bank/_components/pages/DepartmentsPage.tsx')
    for token in (
        '<SectionHeader',
        '<BankTableToolbar',
        '<EnterpriseDataTable',
        '<StatusBadge',
        'setLoadError',
        'onRetry=',
        'ConfirmDialog',
        "can('department.manage_all')",
        "canScope('department.update'",
        'useUrlTableState',
    ):
        assert token in page
    assert '<table' not in page
    assert 'window.alert' not in page
    assert 'window.confirm' not in page


def test_shared_components_are_generic_not_bank_specific():
    section_header = read('frontend/components/layout/SectionHeader.tsx')
    filter_toolbar = read('frontend/components/ui/FilterToolbar.tsx')
    assert 'export function SectionHeader' in section_header
    assert 'export function FilterToolbar' in filter_toolbar
    assert '/bank/' not in section_header
    assert '/bank/' not in filter_toolbar


def test_batch_styles_load_last_and_enforce_content_sized_list_page():
    layout = read('frontend/app/layout.tsx')
    css = read('frontend/styles/bank-redesign-batch-one.css')
    assert layout.rfind("import '../styles/bank-redesign-batch-one.css'") > layout.rfind("import '../styles/frontend-visual-ergonomics-hotfix.css'")
    for token in (
        '.enterprise-content.bank-departments-page',
        'display: flex !important',
        '.bank-departments-page .bank-list-section',
        'height: auto !important',
        '@media (max-width: 1023px)',
        'overflow-x: auto !important',
        'min-width: 940px !important',
    ):
        assert token in css


def test_batch_audit_and_plan_are_committed_with_the_source():
    audit = read('docs/BANK_UX_AUDIT_DESIGN_SYSTEM_IMPLEMENTATION_PLAN_BATCH_1.md')
    for heading in (
        'Workflow map',
        'UX audit',
        'Design system',
        'Implementation plan',
        'Batch 1',
    ):
        assert heading.lower() in audit.lower()
