from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_learning_dashboard_routes_and_export_audit_are_present():
    text = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert "@router.get('/learning/dashboard')" in text
    assert "@router.get('/learning/export.csv')" in text
    assert "@router.get('/classes/{class_id}/video-summary')" in text
    assert "@router.get('/classes/{class_id}/sessions/progress')" in text
    assert "@router.get('/videos/{video_id}/students')" in text
    assert "analytics.learning_behavior.export_csv" in text
    assert "analytics.learning_behavior.view_attention_list" in text
    assert "signals_only_not_violation" in text


def test_learning_dashboard_service_uses_snapshots_not_raw_events_for_dashboard():
    text = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    start = text.index('    def learning_dashboard(')
    end = text.index('    def export_learning_behavior_csv', start)
    body = text[start:end]
    assert 'AnalyticsLearningBehaviorSnapshot' in body
    assert 'AnalyticsTrackingEvent' not in body
    assert 'top_possible_suspicious' in body
    assert 'deadline_attention' in body
    assert 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.' in body


def test_csv_export_uses_safe_vietnamese_display_labels_not_raw_cheating_label():
    text = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    start = text.index('    def export_learning_behavior_csv(')
    end = text.index('    def video_students', start)
    body = text[start:end]
    assert 'classification_display' in body
    assert 'self._safe_label' in body
    assert 'POSSIBLE_CHEATING' not in body
    assert 'không phải kết luận vi phạm' in body


def test_frontend_learning_dashboard_route_is_packaged_and_safe_labels_rendered():
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    assert 'Học online' in page
    assert 'Dấu hiệu bất thường cần kiểm tra' in page
    assert 'Có khả năng treo máy' in page
    assert 'Có dấu hiệu học thật' in page
    assert 'không phải kết luận vi phạm' in page
    lower = page.lower()
    assert 'gian lận' not in lower
    assert 'chắc chắn' not in lower


def test_appshell_links_learning_analytics_dashboard():
    app = (_root() / 'frontend' / 'components' / 'layout' / 'AppShell.tsx').read_text(encoding='utf-8')
    assert "href: '/analytics/learning'" in app
    assert "[/^\\/analytics(?:\\/|$)/, 'view_dashboard']" in app
