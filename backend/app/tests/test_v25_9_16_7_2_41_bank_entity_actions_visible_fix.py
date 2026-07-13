from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v41_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v41_entity_actions_support_inline_table_variant_and_locked_placeholder():
    shared = read('frontend/app/bank/_components/shared.tsx')
    assert "variant = 'menu'" in shared
    assert "variant?: 'menu' | 'inline'" in shared
    assert 'entity-actions-placeholder' in shared
    assert 'lockedLabel = ' in shared
    assert "if (variant === 'inline')" in shared
    assert 'entity-actions-inline' in shared
    assert '>Sửa</button>' in shared
    assert '>Xóa</button>' in shared
    assert 'if (!canManage) return null' not in shared


def test_v41_bank_compact_tables_use_inline_actions_not_hidden_absolute_menu():
    pages = [
        'frontend/app/bank/_components/pages/DepartmentsPage.tsx',
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
    ]
    for page in pages:
        source = read(page)
        assert 'EntityActions variant="inline"' in source
        assert '<th>Thao tác</th>' in source
    assert "lockedLabel={hasPublished ? 'Đã khóa' : 'Không có quyền'}" in read('frontend/app/bank/_components/pages/SubjectVersionsPage.tsx')
    assert "lockedLabel={hasPublished ? 'Đã khóa' : 'Không có quyền'}" in read('frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx')


def test_v41_css_makes_compact_table_actions_visible_inside_action_column():
    css = read('frontend/app/globals.css')
    assert 'v25.9.16.7.2.64.12 — bank compact row actions visible fix' in css
    assert '.bank-multipage .bank-compact-data-table .entity-actions-inline' in css
    assert '.bank-multipage .bank-compact-data-table .entity-actions-placeholder' in css
    assert '.btn.danger-soft' in css
    assert 'min-width: 136px;' in css


def test_v41_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
