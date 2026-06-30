from __future__ import annotations

from pathlib import Path


def test_connector_uses_resolved_course_home_progress_route_before_view_guessing():
    root = Path(__file__).resolve().parents[3]
    plugin = root / 'openedx-connector-plugin' / 'openedx_ai_connector' / 'student_insight.py'
    text = plugin.read_text(encoding='utf-8')

    assert 'def _course_home_resolved_response' in text
    assert "resolve(path)" in text
    assert "'/api/course_home/progress/{course_id_text}'" in text
    assert 'def _authenticate_synthetic_request' in text
    assert 'force_authenticate(request, user=user)' in text
    assert 'CourseHomeProgressRoute:completion_summary' in text
