from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_responsive_ux_css_breakpoints_and_table_safety():
    css = (ROOT / 'frontend/app/globals.css').read_text()
    assert 'responsive device-adaptive UX sweep' in css
    assert '@media (max-width: 1280px)' in css
    assert '@media (max-width: 1024px)' in css
    assert '@media (max-width: 760px)' in css
    assert '@media (max-width: 480px)' in css
    assert 'overflow-x: auto' in css
    assert '-webkit-overflow-scrolling: touch' in css
    assert 'scrollbar-gutter: stable both-edges' in css
    assert '--ux-touch-target: 44px' in css
    assert 'grid-template-columns: repeat(auto-fit' in css
    assert '100dvh' in css


def test_root_layout_has_mobile_viewport_metadata():
    layout = (ROOT / 'frontend/app/layout.tsx').read_text()
    assert "import type { Metadata, Viewport } from 'next'" in layout
    assert 'export const viewport: Viewport' in layout
    assert "width: 'device-width'" in layout
    assert "initialScale: 1" in layout
    assert "viewportFit: 'cover'" in layout


def test_version_is_synchronized_for_current_release():
    assert "app_version: str = '25.9.16.7.2.64.12'" in (ROOT / 'backend/app/core/config.py').read_text()
    assert '"version": "25.9.16.7.2.64.12"' in (ROOT / 'frontend/package.json').read_text()
    assert '25.9.16.7.2.64.12' in (ROOT / 'docker-compose.prod.yml').read_text()
    assert "'25.9.16.7.2.64.12'" in (ROOT / 'frontend/components/layout/AppShell.tsx').read_text()
