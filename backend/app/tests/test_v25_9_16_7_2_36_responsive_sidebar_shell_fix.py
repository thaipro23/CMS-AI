from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v36_version_and_current_docs_are_synchronized():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'APP_VERSION={VERSION}' in read('.env.example')
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')


def test_v36_sidebar_css_overrides_old_two_column_rail_on_desktop():
    css = read('frontend/app/globals.css')
    assert 'v25.9.16.7.2.36 — responsive sidebar shell fix' in css
    v36_css = css.split('v25.9.16.7.2.36 — responsive sidebar shell fix', 1)[1]
    desktop_block = v36_css.split('@media (min-width: 1025px)', 1)[1].split('@media (max-width: 1024px)', 1)[0]
    assert '.product-sidebar.sidebar' in desktop_block
    assert 'overflow-x: hidden' in desktop_block
    assert '.product-nav.grouped-side-nav' in desktop_block
    assert 'flex-direction: column' in desktop_block
    assert '.product-nav .nav-group-items' in desktop_block
    assert 'grid-template-columns: 1fr' in desktop_block
    assert '.product-nav .nav-link' in desktop_block
    assert 'width: 100%' in desktop_block


def test_v36_mobile_sidebar_is_bounded_horizontal_scroll_not_page_overflow():
    css = read('frontend/app/globals.css')
    v36_css = css.split('v25.9.16.7.2.36 — responsive sidebar shell fix', 1)[1]
    mobile_block = v36_css.split('@media (max-width: 1024px)', 1)[1].split('@media (max-width: 480px)', 1)[0]
    assert 'max-width: 100vw' in mobile_block
    assert 'overflow-x: hidden' in mobile_block
    assert 'width: 100% !important' in mobile_block
    assert 'max-width: 100vw !important' in mobile_block
    assert 'display: flex !important' in mobile_block
    assert 'flex-wrap: nowrap' in mobile_block
    assert 'overflow-x: auto' in mobile_block
    assert '.product-nav .nav-group-items' in mobile_block
    assert 'display: contents !important' in mobile_block
    assert '.product-brand.brand::after { display: none; }' in mobile_block
    assert 'flex: 0 0 auto' in mobile_block


def test_v36_changelog_order_and_no_migration():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith(f'## v{VERSION} — {TITLE}')
    assert changelog.index(f'## v{VERSION} — {TITLE}') < changelog.index('## v25.9.16.7.2.36 — Responsive Sidebar Shell Fix + Analytics Orchestrator QA')
    assert '- No migration.' in changelog.split('## v25.9.16.7.2.35', 1)[0]
