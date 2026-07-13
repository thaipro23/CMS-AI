from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v42_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v42_shared_bank_table_toolbar_and_status_filter_are_reusable():
    shared = read('frontend/app/bank/_components/shared.tsx')
    assert 'export type BankTableStatusFilter' in shared
    assert 'export function bankStatusBucket' in shared
    assert 'export function bankStatusMatches' in shared
    assert 'export function BankTableToolbar' in shared
    assert '<option value="published">Đã đưa lên CMS</option>' in shared
    assert '<option value="ready">Sẵn sàng chốt</option>' in shared
    assert '<option value="needs_work">Cần xử lý</option>' in shared
    assert '<option value="empty">Chưa có dữ liệu</option>' in shared
    assert 'bank-table-result-count' in shared
    assert 'Xóa lọc' in shared


def test_v42_bank_hierarchy_pages_use_production_toolbar_and_filtered_tables():
    pages = [
        'frontend/app/bank/_components/pages/DepartmentsPage.tsx',
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
    ]
    for page in pages:
        source = read(page)
        assert 'BankTableToolbar' in source
        assert 'BankTableStatusFilter' in source
        assert 'bankStatusMatches(stats, statusFilter)' in source
        assert "useState<BankTableStatusFilter>('all')" in source
        assert 'resultCount={visible.length}' in source
        assert 'totalCount={summaries.length}' in source
        assert 'bank-production-table' in source
        assert 'SearchActionBar search={search}' not in source
        assert 'entity-card link-card' not in source


def test_v42_css_sticky_stt_and_action_columns_without_page_overflow():
    css = read('frontend/app/globals.css')
    assert 'v25.9.16.7.2.64.12 — bank table production ux' in css
    assert '.bank-table-toolbar' in css
    assert '.bank-table-toolbar-fields' in css
    assert '.bank-table-result-count' in css
    assert '.bank-multipage .bank-production-table th:last-child' in css
    assert 'position: sticky;' in css
    assert 'right: 0;' in css
    assert '.bank-multipage .bank-production-table th:first-child' in css
    assert 'left: 0;' in css
    assert '@media (max-width: 900px)' in css


def test_v42_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
