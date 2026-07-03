from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from app.services.learning_analytics.learning_behavior_classifier import BehaviorInput, classify_learning_behavior
from app.services.learning_analytics.quiz_attempt_analyzer import EventLike, build_quiz_attempt_features
from app.services.learning_analytics.session_deadline_mapper import build_session_mappings_from_blocks
from app.services.learning_analytics.tracking_event_parser import parse_tracking_log_line
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress

ROOT = Path(__file__).resolve().parents[3]


def test_video_quality_prevents_high_completion_low_watch_getting_real_learning_score():
    result = classify_learning_behavior(BehaviorInput(
        total_events=50,
        total_sessions=3,
        sessions_started=3,
        sessions_completed_on_time=3,
        video_before_quiz_count=3,
        total_videos_seen=3,
        total_videos_completed=3,
        avg_video_completion_percent=95,
        avg_estimated_watch_percent=5,
        suspicious_video_count=3,
        extra_reasons=['HIGH_COMPLETION_LOW_WATCH_TIME', 'LARGE_SEEK_JUMP'],
    ))
    assert result.real_learning_score < 35
    assert result.suspicious_score >= 45
    assert result.classification != 'LIKELY_REAL_LEARNING'
    assert result.classification != 'POSSIBLE_CHEATING'


def test_suspicious_score_is_rate_based_not_absolute_count():
    severe_small_total = classify_learning_behavior(BehaviorInput(
        total_events=80,
        total_sessions=3,
        sessions_started=3,
        total_videos_seen=3,
        suspicious_video_count=3,
        total_quiz_sessions=3,
        quiz_before_video_count=3,
        total_quiz_attempts=3,
        suspicious_quiz_speed_count=3,
        crammed_low_watch_session_count=3,
        extra_reasons=['HIGH_COMPLETION_LOW_WATCH_TIME', 'QUIZ_BEFORE_VIDEO'],
    ))
    diluted_large_total = classify_learning_behavior(BehaviorInput(
        total_events=80,
        total_sessions=30,
        sessions_started=30,
        total_videos_seen=30,
        suspicious_video_count=3,
        total_quiz_sessions=30,
        quiz_before_video_count=3,
        total_quiz_attempts=30,
        suspicious_quiz_speed_count=3,
        crammed_low_watch_session_count=3,
        extra_reasons=['HIGH_COMPLETION_LOW_WATCH_TIME', 'QUIZ_BEFORE_VIDEO'],
    ))
    assert severe_small_total.suspicious_score > diluted_large_total.suspicious_score * 5


def test_dynamic_watch_cap_marks_long_passive_segment_but_does_not_cut_normal_long_video_with_seek():
    base = datetime(2026, 7, 1, 8, 0, 0)
    passive = calculate_video_progress([
        VideoEventInput('play_video', base, 0, 1800),
        VideoEventInput('pause_video', base + timedelta(minutes=50), 1700, 1800),
    ])
    assert passive.long_passive_segment_count == 1
    assert 'LONG_PASSIVE_PLAYBACK' in passive.reason_codes

    interactive = calculate_video_progress([
        VideoEventInput('play_video', base, 0, 1800),
        VideoEventInput('seek_video', base + timedelta(minutes=20), 1200, 1800),
        VideoEventInput('pause_video', base + timedelta(minutes=30), 1700, 1800),
    ])
    assert interactive.long_passive_segment_count == 0
    assert interactive.estimated_watch_seconds >= 1700


def test_parser_accepts_ulmo_quiz_session_itembank_submit_and_noise_filtering():
    def line(event_type: str, event: dict, source: str = 'server') -> str:
        payload = {
            'username': 'sv001',
            'event_source': source,
            'context': {'user_id': 10, 'course_id': 'course-v1:FPT+COM1071+SU26'},
            'event_type': event_type,
            'time': '2026-07-01T08:00:00Z',
            'page': 'https://cms-test.poly.edu.vn/courses/course-v1:FPT+COM1071+SU26/xblock/block-v1:FPT+COM1071+SU26+type@sequential+block@u1',
            'event': json.dumps(event),
        }
        return 'INFO tracking - ' + json.dumps(payload)

    assert parse_tracking_log_line(line('/api/unit-reset/v1/quiz-session/start', {'unit_usage_key': 'u1'})).event_type.endswith('/start')
    assert parse_tracking_log_line(line('edx.itembankblock.content.assigned', {'unit_usage_key': 'u1', 'problem_usage_key': 'p1'})).event_type == 'edx.itembankblock.content.assigned'
    assert parse_tracking_log_line(line('edx.grades.problem.submitted', {'unit_usage_key': 'u1', 'problem_id': 'p1'})).event_source == 'server'
    noise = 'INFO tracking - ' + json.dumps({'event_type': 'page_close', 'page': 'https://cms-test.poly.edu.vn/theming/asset/favicon.ico', 'event': '{}'})
    assert parse_tracking_log_line(noise) is None


def test_quiz_attempt_state_machine_ignores_null_user_status_and_does_not_join_across_reset():
    base = datetime(2026, 7, 1, 8, 0, 0)
    events = [
        EventLike('/api/unit-reset/v1/quiz-session/status', 'server', base, None, 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1'}, {}, {}),
        EventLike('/api/unit-reset/v1/quiz-session/start', 'server', base + timedelta(seconds=1), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1'}, {}, {}),
        EventLike('edx.itembankblock.content.assigned', 'server', base + timedelta(seconds=2), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1', 'problem_usage_key': 'p1'}, {}, {}),
        EventLike('edx.grades.problem.submitted', 'server', base + timedelta(seconds=4), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1', 'problem_id': 'p1'}, {}, {}),
        EventLike('/api/unit-reset/v1/quiz-session/reset', 'server', base + timedelta(seconds=10), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1'}, {}, {}),
        EventLike('/api/unit-reset/v1/quiz-session/start', 'server', base + timedelta(seconds=11), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1'}, {}, {}),
        EventLike('edx.itembankblock.content.assigned', 'server', base + timedelta(seconds=12), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1', 'problem_usage_key': 'p2'}, {}, {}),
        EventLike('edx.grades.problem.submitted', 'server', base + timedelta(seconds=15), '10', 'sv001', 'course-v1:FPT+COM1071+SU26', None, {'unit_usage_key': 'u1', 'problem_id': 'p2'}, {}, {}),
    ]
    features = build_quiz_attempt_features(events)
    assert len(features) == 2
    assert features[0].attempt_no == 1
    assert features[1].attempt_no == 2
    assert features[0].assigned_problem_usage_keys == ['p1']
    assert features[1].assigned_problem_usage_keys == ['p2']


def test_session_mapper_classifies_final_test_and_assignment_not_learning_session():
    blocks = [
        {'id': 's1', 'block_type': 'sequential', 'display_name': 'Bài 1', 'children': [{'id': 'v1', 'block_type': 'video'}]},
        {'id': 's2', 'block_type': 'sequential', 'display_name': 'Final test', 'children': [{'id': 'qf', 'block_type': 'problem'}]},
        {'id': 's3', 'block_type': 'sequential', 'display_name': 'Assignment', 'children': [{'id': 'qa', 'block_type': 'problem'}]},
    ]
    mappings = build_session_mappings_from_blocks('course-v1:FPT+COM1071+SU26', blocks)
    assert mappings[0].session_type == 'LEARNING_SESSION'
    assert mappings[1].session_type == 'FINAL_TEST'
    assert mappings[2].session_type == 'ASSIGNMENT'


def test_codebase_uses_possible_anomaly_in_new_classifier_and_keeps_soft_ui_label():
    classifier = (ROOT / 'backend/app/services/learning_analytics/learning_behavior_classifier.py').read_text(encoding='utf-8')
    analytics_page = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text(encoding='utf-8')
    assert "classification = 'POSSIBLE_ANOMALY'" in classifier
    assert 'POSSIBLE_CHEATING' in classifier  # backward-compatible read only
    assert 'Dấu hiệu bất thường cần kiểm tra' in analytics_page
