from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_backend_exposes_subject_class_behavior_overview():
    route = (ROOT / 'backend/app/api/routes/learning_analytics.py').read_text()
    service = (ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py').read_text()

    assert "/subjects/{subject_id}/classes/learning-behavior/overview" in route
    assert "class_behavior_overview(" in route
    assert "allowed_class_ids = _allowed_class_ids_for_analytics" in route
    assert "def class_behavior_overview(" in service
    assert "AcademicClassStudent.class_id" in service
    assert "AnalyticsLearningBehaviorSnapshot.class_id.in_(class_ids)" in service
    assert "snapshot/aggregate tables" in service


def test_frontend_flow_has_class_overview_before_student_detail():
    page = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text()
    api = (ROOT / 'frontend/lib/api.ts').read_text()
    types = (ROOT / 'frontend/types/index.ts').read_text()

    assert "getAnalyticsSubjectClassBehaviorOverview" in page
    assert "Danh sách lớp" in page
    assert "Chi tiết lớp" in page
    assert "Xem kết quả" in page
    assert "selectedClassOverview" in page
    assert "Lớp\n          <select" not in page
    assert "/analytics/subjects/${encodeURIComponent(subjectId)}/classes/learning-behavior/overview" in api
    assert "AnalyticsClassBehaviorOverviewItem" in types


def test_learning_behavior_class_flow_css_present():
    css = (ROOT / 'frontend/app/globals.css').read_text()
    assert "Learning behavior" in css
    assert ".analytics-class-overview-table" in css
    assert ".analytics-class-selected-row" in css
