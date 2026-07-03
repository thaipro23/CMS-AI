from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.38'
TITLE = 'Bank Compact Table UX + Sidebar Taxonomy'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v38_version_and_docs_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'APP_VERSION={VERSION}' in read('.env.example')
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_38.md')


def test_v38_sidebar_group_taxonomy_matches_bank_training_admin_model():
    shell = read('frontend/components/layout/AppShell.tsx')
    assert "{ key: 'work', label: 'Quản lý ngân hàng đề' }" in shell
    assert "{ key: 'operations', label: 'Quản lý sinh viên' }" in shell
    assert "{ key: 'admin', label: 'Quản trị' }" in shell
    for href in ['/premises', '/semesters', '/ap-sync', '/jobs', '/audit']:
        line = next(line for line in shell.splitlines() if f"href: '{href}'" in line)
        assert "group: 'admin'" in line
    for href in ['/student-management', '/teacher-management', '/analytics/learning']:
        line = next(line for line in shell.splitlines() if f"href: '{href}'" in line)
        assert "group: 'operations'" in line


def test_v38_bank_hierarchy_pages_use_compact_tables_not_large_card_lists():
    files = [
        'frontend/app/bank/_components/pages/DepartmentsPage.tsx',
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
    ]
    for file in files:
        source = read(file)
        assert 'bank-compact-table-wrap' in source
        assert 'bank-compact-data-table' in source
        assert '<th>STT</th>' in source
        assert 'bank-table-link' in source
        assert 'bank-row-status' in source
        assert 'entity-card link-card' not in source
        assert 'entity-list horizontal multipage-list' not in source


def test_v38_chapter_workspace_embeds_stats_in_lesson_header_and_removes_large_release_block():
    source = read('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    assert 'chapter-inline-stats' in source
    assert 'Tổng câu <b>{usedQuestionCount}/{chapterQuestionLimit}</b>' in source
    assert "Bộ đề <b>{publishedRelease ? 'Đã đưa lên CMS' : latestRelease ? 'Đã chốt' : 'Chưa chốt'}</b>" in source
    assert '<section className="summary-grid compact-summary">' not in source
    assert 'nextReleaseText(publishedRelease || latestRelease)' not in source


def test_v38_css_locks_compact_bank_table_and_inline_chapter_stats():
    css = read('frontend/app/globals.css')
    assert 'v25.9.16.7.2.38 — compact bank table ux' in css
    assert '.bank-multipage .bank-compact-data-table' in css
    assert '.bank-table-link' in css
    assert '.bank-row-status' in css
    assert '.chapter-inline-stats' in css
    assert '@media (max-width: 760px)' in css


def test_v38_changelog_order_and_no_migration():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith(f'## v{VERSION} — {TITLE}')
    assert changelog.index(f'## v{VERSION} — {TITLE}') < changelog.index('## v25.9.16.7.2.37 — Analytics Class Result Doctor + Production Readiness Repair')
    assert '- No migration.' in changelog.split('## v25.9.16.7.2.37', 1)[0]
