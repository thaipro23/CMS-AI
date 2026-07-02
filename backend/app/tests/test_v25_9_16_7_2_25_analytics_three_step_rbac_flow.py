from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_analytics_learning_page_is_three_step_flow_and_not_one_page_combo():
    page = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text(encoding='utf-8')
    assert "type AnalyticsFlowStep = 'subjects' | 'classes' | 'results'" in page
    assert "1. Môn" in page
    assert "2. Lớp" in page
    assert "3. Xem kết quả" in page
    assert "step === 'subjects'" in page
    assert "step === 'classes'" in page
    assert "step === 'results'" in page
    assert "Xem lớp" in page
    assert "Xem kết quả" in page
    assert "Quay lại lớp" in page
    assert "Quay lại môn" in page


def test_analytics_learning_supports_all_campus_and_url_state_for_refresh():
    page = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text(encoding='utf-8')
    assert "queryCampusRaw === 'all'" in page
    assert '<option value="">Tất cả cơ sở</option>' in page
    assert "params.set('step', nextStep)" in page
    assert "params.set('campus', nextCampus || 'all')" in page
    assert "router.replace(`/analytics/learning?${params.toString()}`" in page


def test_analytics_backend_returns_permission_scope_and_keeps_backend_enforcement():
    route = (ROOT / 'backend/app/api/routes/learning_analytics.py').read_text(encoding='utf-8')
    assert 'def _analytics_permission_scope' in route
    assert "'enforced_by_backend': True" in route
    assert "result['permission_scope'] = _analytics_permission_scope(db, user)" in route
    assert '_assert_analytics_class_access(db, user, class_id)' in route
    assert 'allowed_class_ids = _allowed_class_ids_for_analytics(db, user)' in route


def test_analytics_class_overview_response_type_exposes_permission_scope():
    types = (ROOT / 'frontend/types/index.ts').read_text(encoding='utf-8')
    assert 'export type AnalyticsLearningPermissionScope' in types
    assert 'permission_scope?: AnalyticsLearningPermissionScope' in types
