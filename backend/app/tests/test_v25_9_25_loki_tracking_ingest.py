from __future__ import annotations

import json

from app.services.learning_analytics.loki_tracking_reader import LokiTrackingLogReader
from app.services.learning_analytics.tracking_event_parser import parse_tracking_log_line


def _line(event_type: str = 'custom_learning_event') -> str:
    payload = {
        'username': 'sv001',
        'context': {
            'user_id': 101,
            'course_id': 'course-v1:FPT+COM1071+FA26',
            'org_id': 'FPT',
        },
        'event_type': event_type,
        'time': '2026-09-25T04:00:00Z',
        'page': 'https://cms.fpl.edu.vn/courses/course-v1:FPT+COM1071+FA26/courseware/unit',
        'event': {'value': 'kept-for-future-analysis'},
    }
    return json.dumps(payload)


def test_parser_can_retain_all_event_types_for_loki_history():
    assert parse_tracking_log_line(_line()) is None

    parsed = parse_tracking_log_line(_line(), relevant_only=False)

    assert parsed is not None
    assert parsed.event_type == 'custom_learning_event'
    assert parsed.username == 'sv001'
    assert parsed.course_id == 'course-v1:FPT+COM1071+FA26'
    assert parsed.raw_event == {'value': 'kept-for-future-analysis'}


def test_loki_flatten_keeps_stream_metadata_and_sorts_forward():
    payload = {
        'status': 'success',
        'data': {
            'resultType': 'streams',
            'result': [
                {
                    'stream': {'pod': 'lms-abc', 'app': 'lms'},
                    'values': [['200', _line('problem_check')], ['100', _line('play_video')]],
                },
                {
                    'stream': {'pod': 'lms-worker-xyz', 'app': 'lms-worker'},
                    'values': [['150', _line('edx.grades.problem.submitted')]],
                },
            ],
        },
    }

    rows = LokiTrackingLogReader._flatten(payload)

    assert [row.timestamp_ns for row in rows] == [100, 150, 200]
    assert rows[0].pod == 'lms-abc'
    assert rows[0].app == 'lms'
    assert rows[1].pod == 'lms-worker-xyz'
    assert rows[1].app == 'lms-worker'


def test_loki_reader_accepts_documented_production_query_shape():
    reader = LokiTrackingLogReader(
        base_url='http://loki.logging.svc.cluster.local:3100',
        query='{namespace="openedx", app=~"lms|lms-worker"} |= "event_type"',
        window_seconds=600,
        lag_seconds=120,
        limit=1000,
        max_pages=10,
        max_lines=5000,
    )

    assert reader.base_url == 'http://loki.logging.svc.cluster.local:3100'
    assert reader.window_ns == 600 * 1_000_000_000
    assert reader.lag_ns == 120 * 1_000_000_000
    assert reader.limit == 1000
