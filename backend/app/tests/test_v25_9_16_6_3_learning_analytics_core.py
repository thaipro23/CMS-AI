from __future__ import annotations

from datetime import datetime, timedelta
import json

from app.services.learning_analytics.tracking_event_parser import parse_tracking_log_line
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress
from app.services.learning_analytics.session_deadline_mapper import build_session_mappings_from_blocks, session_week_pattern, week_for_session
from app.services.learning_analytics.learning_behavior_classifier import BehaviorInput, classify_learning_behavior, DISPLAY_LABELS


def _line(event_type='play_video', event=None, time='2026-07-01T08:00:00Z'):
    payload = {
        'username': 'duongddph69321',
        'context': {'user_id': 79, 'course_id': 'course-v1:FPT+COM1071+SU26', 'org_id': 'FPT'},
        'event_type': event_type,
        'time': time,
        'session': 'sess-1',
        'page': 'https://cms-test.poly.edu.vn/courses/course-v1:FPT+COM1071+SU26/courseware/block-v1:video@v1',
        'event': json.dumps(event or {'id': 'v1', 'code': 'v1', 'duration': 1010, 'currentTime': 1009}),
    }
    return '2026-07-01 08:00:00,000 INFO 1 [tracking] logger.py:41 - ' + json.dumps(payload)


def test_tracking_parser_prefix_and_nested_event_current_time():
    parsed = parse_tracking_log_line(_line())
    assert parsed is not None
    assert parsed.username == 'duongddph69321'
    assert parsed.course_id == 'course-v1:FPT+COM1071+SU26'
    assert parsed.event_type == 'play_video'
    assert parsed.video_duration_seconds == 1010
    assert parsed.current_time_seconds == 1009
    assert parsed.video_id == 'v1'
    assert len(parsed.raw_line_hash) == 64


def test_tracking_parser_current_time_snake_case():
    parsed = parse_tracking_log_line(_line(event={'id': 'v2', 'duration': 120, 'current_time': 44}))
    assert parsed.current_time_seconds == 44
    assert parsed.video_id == 'v2'


def test_video_completion_1010_1009_is_about_99_9():
    result = calculate_video_progress([
        VideoEventInput('play_video', datetime(2026, 7, 1, 8, 0, 0), 0, 1010),
        VideoEventInput('pause_video', datetime(2026, 7, 1, 8, 5, 0), 1009, 1010),
    ])
    assert 99.8 <= result.completion_percent <= 100
    assert result.is_completed is True


def test_video_watch_segment_5_minutes():
    result = calculate_video_progress([
        VideoEventInput('play_video', datetime(2026, 7, 1, 8, 0, 0), 0, 1000),
        VideoEventInput('pause_video', datetime(2026, 7, 1, 8, 5, 0), 300, 1000),
    ])
    assert 299 <= result.estimated_watch_seconds <= 310


def test_large_seek_jump_and_high_completion_low_watch_time():
    result = calculate_video_progress([
        VideoEventInput('play_video', datetime(2026, 7, 1, 8, 0, 0), 0, 1010),
        VideoEventInput('pause_video', datetime(2026, 7, 1, 8, 0, 5), 985, 1010),
    ])
    assert 'LARGE_SEEK_JUMP' in result.reason_codes
    assert 'HIGH_COMPLETION_LOW_WATCH_TIME' in result.reason_codes
    assert result.is_suspicious is True


def test_deadline_patterns_12_and_11_sessions():
    assert session_week_pattern(12) == [2, 2, 2, 2, 2, 2]
    assert session_week_pattern(11) == [2, 2, 2, 2, 2, 1]
    assert week_for_session(1, 12) == 1
    assert week_for_session(2, 12) == 1
    assert week_for_session(11, 11) == 6


def test_build_session_mapping_video_and_quiz():
    blocks = [
        {'id': 's1', 'block_type': 'sequential', 'display_name': 'Bài 1', 'children': [
            {'id': 'v1', 'block_type': 'video', 'display_name': 'Phần 1'},
            {'id': 'v2', 'block_type': 'video', 'display_name': 'Phần 2'},
            {'id': 'q1', 'block_type': 'problem', 'display_name': 'Quiz cuối Bài 1'},
        ]},
        {'id': 's2', 'block_type': 'sequential', 'display_name': 'Bài 2', 'children': []},
    ]
    mappings = build_session_mappings_from_blocks('course-v1:FPT+COM1071+SU26', blocks, course_start_at=datetime(2026, 6, 1))
    assert mappings[0].session_index == 1
    assert mappings[0].week_index == 1
    assert len(mappings[0].videos) == 2
    assert mappings[0].quiz.usage_key == 'q1'


def test_classifier_likely_real_learning():
    result = classify_learning_behavior(BehaviorInput(
        total_events=50,
        total_sessions=4,
        sessions_started=4,
        sessions_completed_on_time=4,
        video_before_quiz_count=4,
        total_videos_seen=8,
        total_videos_completed=8,
        avg_video_completion_percent=95,
        avg_estimated_watch_percent=82,
    ))
    assert result.classification == 'LIKELY_REAL_LEARNING'
    assert result.display_label == 'Có dấu hiệu học thật'


def test_classifier_possible_idle():
    result = classify_learning_behavior(BehaviorInput(
        total_events=30,
        total_sessions=2,
        sessions_started=2,
        total_videos_seen=8,
        total_videos_completed=8,
        avg_video_completion_percent=95,
        avg_estimated_watch_percent=92,
        long_passive_video_count=3,
    ))
    assert result.classification == 'POSSIBLE_IDLE'
    assert result.display_label == 'Có khả năng treo máy'


def test_classifier_possible_cheating_frontend_label_is_soft():
    result = classify_learning_behavior(BehaviorInput(
        total_events=40,
        total_sessions=6,
        sessions_started=6,
        total_videos_seen=10,
        total_videos_completed=10,
        avg_video_completion_percent=98,
        avg_estimated_watch_percent=10,
        suspicious_video_count=3,
        quiz_before_video_count=2,
        crammed_session_count=2,
        extra_reasons=['LARGE_SEEK_JUMP'],
    ))
    assert result.classification == 'POSSIBLE_CHEATING'
    assert result.display_label == 'Dấu hiệu bất thường cần kiểm tra'
    assert 'cheating' not in result.display_label.lower()


def test_classifier_insufficient_data():
    result = classify_learning_behavior(BehaviorInput(total_events=1, only_caption_events=True))
    assert result.classification == 'INSUFFICIENT_DATA'
    assert result.display_label == 'Chưa đủ dữ liệu'
