from __future__ import annotations

import pytest

from app.services.openedx_student_insight import OpenEdXConnectorClient


@pytest.mark.parametrize('read_consistency', ['replica', 'primary_after_enrollment'])
def test_class_analytics_sends_and_returns_read_consistency(read_consistency):
    client = object.__new__(OpenEdXConnectorClient)
    client.class_analytics_endpoint = '/api/ai-connector/v1/class-analytics'
    client.timeout_seconds = 30
    client.configured = lambda: True
    captured: dict = {}

    def fake_post_json(**kwargs):
        captured.update(kwargs)
        return {
            'ok': True,
            'course_id': kwargs['body']['course_id'],
            'read_consistency': kwargs['body']['read_consistency'],
            'results': [],
        }

    client._post_json = fake_post_json
    result = client.class_analytics_payload(
        course_id='course-v1:FPL+TEST+FA26',
        students=[{'username': 'PH12345'}],
        read_consistency=read_consistency,
    )

    assert captured['body']['read_consistency'] == read_consistency
    assert result['read_consistency'] == read_consistency
