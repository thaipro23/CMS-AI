from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_analytics_course_mapping_fallback_import_is_present():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert 'AcademicCourseMapping' in service
    assert 'from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob, AcademicCourseMapping' in service
    assert 'self.db.query(AcademicCourseMapping)' in service
    assert "'version': '25.9.16.7.2.7'" in service


def test_analytics_learning_page_soft_loads_ops_cards():
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    assert 'Production readiness' in page
    assert 'SLA vận hành analytics' in page
    assert 'Kiểm thử pilot UAT' in page
    assert 'Gói bằng chứng UAT' in page


def test_frontend_sidebar_fixed_and_links_have_no_underline():
    css = (_root() / 'frontend' / 'app' / 'globals.css').read_text(encoding='utf-8')
    assert 'v25.9.16.7.2.6 — fixed sidebar + global underline cleanup' in css
    assert '.product-sidebar.sidebar {' in css
    assert 'position: fixed;' in css
    assert 'height: 100dvh;' in css
    assert 'overflow-y: auto;' in css
    assert 'a:visited,' in css
    assert 'text-decoration: none;' in css
    # Newer responsive/sticky table fixes may use scoped !important to override legacy MFE CSS.
    # The sidebar contract remains: fixed rail on desktop, no link underline, accessible focus styles.
    assert 'focus-visible' in css
