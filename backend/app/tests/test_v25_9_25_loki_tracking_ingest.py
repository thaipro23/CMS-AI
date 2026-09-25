from __future__ import annotations

import json
from datetime import datetime

from app.services.learning_analytics.loki_tracking_reader import LokiTrackingLogReader
from app.services.learning_analytics.tracking_event_parser import parse_tracking_log_line
from app.services.learning_analytics.quiz_attempt_analyzer import EventLike, _submission_score, build_quiz_attempt_features


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


def test_parser_rejects_non_analytics_event_types():
    assert parse_tracking_log_line(_line()) is None


def test_parser_rejects_long_openedx_route_before_database_insert():
    long_route = (
        '/courses/course-v1:FPL+VIE108+FA26/xblock/'
        'block-v1:FPL+VIE108+FA26+type@openassessment+block@28318ce090074c15af84992946cafb11/'
        'handler/render_peer_assessment'
    )

    assert len(long_route) > 120
    assert parse_tracking_log_line(_line(long_route)) is None


def test_parser_keeps_learning_analytics_event():
    parsed = parse_tracking_log_line(_line('problem_check'))

    assert parsed is not None
    assert parsed.event_type == 'problem_check'
    assert parsed.username == 'sv001'
    assert parsed.course_id == 'course-v1:FPT+COM1071+FA26'


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


def test_weighted_problem_score_keeps_zero_earned_value():
    event = EventLike(
        event_type='edx.grades.problem.submitted',
        event_source='openedx_tracking_loki',
        event_time=None,
        user_id='101',
        username='sv001',
        course_id='course-v1:FPT+COM1071+FA26',
        page_url=None,
        raw_event={'weighted_earned': 0, 'weighted_possible': 1},
        raw_context={},
        raw_json={},
    )

    earned, possible = _submission_score(event)

    assert earned == 0.0
    assert possible == 1.0


def test_parser_reads_production_quiz_status_get_params_and_referer():
    payload = {
        'username': 'TH09593',
        'context': {'user_id': 13668, 'course_id': '', 'org_id': ''},
        'event_type': '/api/unit-reset/v1/quiz-session/status',
        'time': '2026-09-25T06:55:31.128433+00:00',
        'referer': 'https://edx.cms.fpl.edu.vn/',
        'event': json.dumps({
            'GET': {
                'course_id': ['course-v1:FPS+COM1091+FA26'],
                'sequence_usage_key': ['block-v1:FPS+COM1091+FA26+type@sequential+block@quiz-4-f6e6f13e'],
                'unit_usage_key': ['block-v1:FPS+COM1091+FA26+type@vertical+block@quiz-964a50b2'],
            },
            'POST': {},
        }),
    }
    line = '2026-09-25 06:55:31,128 INFO 39 [tracking] logger.py:41 - ' + json.dumps(payload)

    parsed = parse_tracking_log_line(line)

    assert parsed is not None
    assert parsed.course_id == 'course-v1:FPS+COM1091+FA26'
    assert parsed.user_id == '13668'
    assert parsed.page_url == 'https://edx.cms.fpl.edu.vn/'


def test_parser_reads_worker_user_id_from_nested_grade_event():
    payload = {
        'username': '',
        'context': {'course_id': 'course-v1:FPL+DOM1041+FA26', 'org_id': 'FPL'},
        'event_type': 'edx.grades.problem.submitted',
        'time': '2026-09-25T06:42:02.807362+00:00',
        'referer': 'https://cms.fpl.edu.vn/xblock/block-v1:FPL+DOM1041+FA26+type@vertical+block@quiz-a',
        'event': {
            'user_id': '18067',
            'course_id': 'course-v1:FPL+DOM1041+FA26',
            'problem_id': 'block-v1:FPL+DOM1041+FA26+type@problem+block@p1',
            'weighted_earned': 0,
            'weighted_possible': 1,
        },
    }

    parsed = parse_tracking_log_line(json.dumps(payload))

    assert parsed is not None
    assert parsed.user_id == '18067'
    assert parsed.page_url.endswith('type@vertical+block@quiz-a')


def test_quiz_status_and_submitted_problem_correlate_to_one_vertical_attempt():
    course = 'course-v1:FPS+COM1091+FA26'
    unit = 'block-v1:FPS+COM1091+FA26+type@vertical+block@quiz-964a50b2'
    sequence = 'block-v1:FPS+COM1091+FA26+type@sequential+block@quiz-4-f6e6f13e'
    status = EventLike(
        event_type='/api/unit-reset/v1/quiz-session/status',
        event_source='server',
        event_time=datetime(2026, 9, 25, 6, 55, 31),
        user_id='13668',
        username='TH09593',
        course_id=course,
        page_url=None,
        raw_event={'GET': {'course_id': [course], 'sequence_usage_key': [sequence], 'unit_usage_key': [unit]}, 'POST': {}},
        raw_context={},
        raw_json={},
    )
    submitted = EventLike(
        event_type='edx.grades.problem.submitted',
        event_source='server',
        event_time=datetime(2026, 9, 25, 6, 55, 35),
        user_id='13668',
        username='TH09593',
        course_id=course,
        page_url='https://cms.fpl.edu.vn/xblock/' + unit + '?format=Quiz',
        raw_event={
            'problem_id': 'block-v1:FPS+COM1091+FA26+type@problem+block@p1',
            'weighted_earned': 0,
            'weighted_possible': 1,
        },
        raw_context={},
        raw_json={},
    )

    features = build_quiz_attempt_features([status, submitted])

    assert len(features) == 1
    feature = features[0]
    assert feature.unit_usage_key == unit
    assert feature.sequence_usage_key == sequence
    assert feature.score_earned == 0.0
    assert feature.score_possible == 1.0
    assert len(feature.submissions) == 1
    assert feature.submissions[0]['problem_usage_key'].endswith('type@problem+block@p1')


def test_canonical_grade_event_suppresses_browser_submission_duplicate():
    course = 'course-v1:FPS+COM1091+FA26'
    unit = 'block-v1:FPS+COM1091+FA26+type@vertical+block@quiz-964a50b2'
    browser = EventLike(
        event_type='problem_check',
        event_source='browser',
        event_time=datetime(2026, 9, 25, 6, 55, 34),
        user_id='13668', username='TH09593', course_id=course,
        page_url='https://cms.fpl.edu.vn/xblock/' + unit + '?format=Quiz',
        raw_event={'value': 'input_problem=choice_1'},
        raw_context={}, raw_json={},
    )
    canonical = EventLike(
        event_type='edx.grades.problem.submitted',
        event_source='server',
        event_time=datetime(2026, 9, 25, 6, 55, 35),
        user_id='13668', username='TH09593', course_id=course,
        page_url='https://cms.fpl.edu.vn/xblock/' + unit + '?format=Quiz',
        raw_event={
            'problem_id': 'block-v1:FPS+COM1091+FA26+type@problem+block@p1',
            'weighted_earned': 1,
            'weighted_possible': 1,
        },
        raw_context={}, raw_json={},
    )

    features = build_quiz_attempt_features([browser, canonical])

    assert len(features) == 1
    assert len(features[0].submissions) == 1
    assert features[0].submissions[0]['event_type'] == 'edx.grades.problem.submitted'
    assert features[0].evidence['server_canonical_submission'] is True
    assert features[0].evidence['fallback_submission_count'] == 1
