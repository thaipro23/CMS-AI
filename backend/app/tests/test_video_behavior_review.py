"""Repeated seeking needs review even when quiz telemetry dilutes the risk score."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.learning_analytics import (AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentVideoProgress, AnalyticsStudentSessionProgress)
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
from app.services.learning_analytics.presentation import behavior_freshness
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress, has_observed_watch_timing, measure_playback


@pytest.fixture
def service(monkeypatch):
    engine = create_engine('sqlite://')
    for model in (AnalyticsLearningBehaviorSnapshot, AnalyticsStudentVideoProgress, AnalyticsStudentSessionProgress):
        model.__table__.create(engine)
    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)
        monkeypatch.setattr(service, '_student_usernames_for_class', lambda **_: ['learner'])
        monkeypatch.setattr(service, '_events_count_by_username', lambda **_: {'learner': 100})
        monkeypatch.setattr(service, '_quiz_attempts_by_username', lambda **_: {})
        monkeypatch.setattr(service, 'get_session_structure', lambda **_: [])
        for index in range(1, 4):
            db.add(AnalyticsStudentSessionProgress(course_id='course', username='learner',
                session_key=f'lesson{index}', session_index=index, started_at=datetime(2026, 10, 1),
                deadline_at=datetime(2026, 12, 1)))
        db.commit()
        yield service
    engine.dispose()


def seed_videos(service, *, count=9, low_count=7, timing=True, duration=1000):
    for index in range(count):
        low = index < low_count
        start = datetime(2026, 10, 1)
        result = calculate_video_progress([
            VideoEventInput('play_video', start, 0, duration),
            VideoEventInput('seek_video', start + timedelta(seconds=1), 999 if low else 400, duration),
            VideoEventInput('pause_video', start + timedelta(seconds=2 if low else 1001), 999 if low else 1000, duration),
        ])
        service.db.add(AnalyticsStudentVideoProgress(course_id='course', username='learner',
            video_id=f'video{index}', session_index=index % 3 + 1, duration_seconds=duration,
            completion_percent=99.9 if low else 100, estimated_watch_seconds=1 if low else 1000,
            estimated_watch_percent=.1 if low else 100, is_completed=True, is_suspicious=low,
            suspicious_reason='HIGH_COMPLETION_LOW_WATCH_TIME,LARGE_SEEK_JUMP' if low else '',
            evidence_json={**result.evidence, 'event_count': 6} if timing else {'event_count': 6}))
    service.db.commit()


def recalculate(service):
    service.recalculate_learning_behavior(class_id=None, course_id='course',
        refresh_session_progress=False, refresh_ml=False)
    return service.db.query(AnalyticsLearningBehaviorSnapshot).one()


def test_repeated_measured_seeking_gets_review_at_35_percent_score(service):
    seed_videos(service)
    row = recalculate(service)
    assert row.suspicious_score == 35
    assert row.classification == 'POSSIBLE_ANOMALY'
    assert row.recommended_action == 'TEACHER_REVIEW'
    assert 'REPEATED_HIGH_COMPLETION_LOW_WATCH' in row.reason_codes
    assert row.evidence_json['measured_low_watch_video_count'] == 7


def test_healthy_videos_do_not_erase_a_repeated_measured_seek_pattern(service):
    seed_videos(service, count=30, low_count=3)
    assert recalculate(service).recommended_action == 'TEACHER_REVIEW'


@pytest.mark.parametrize('timing,duration', [(False, 1000), (True, None)])
def test_missing_timing_or_duration_is_not_evidence_of_zero_watch(service, timing, duration):
    seed_videos(service, timing=timing, duration=duration)
    row = recalculate(service)
    assert row.classification == 'INSUFFICIENT_DATA'
    assert row.recommended_action == 'INSUFFICIENT_DATA_RECHECK_LATER'
    assert row.evidence_json['measured_low_watch_video_count'] == 0


def test_single_measured_seek_does_not_trigger_repeated_review(service):
    seed_videos(service, count=9, low_count=1)
    assert recalculate(service).classification != 'POSSIBLE_ANOMALY'


def test_repeated_seek_in_only_one_lesson_does_not_trigger_course_review(service):
    seed_videos(service)
    for row in service.db.query(AnalyticsStudentVideoProgress):
        row.session_index = 1
    service.db.commit()
    assert recalculate(service).classification != 'POSSIBLE_ANOMALY'


def test_observed_media_progress_prevents_false_low_watch_when_legacy_estimate_is_zero(service):
    seed_videos(service)
    for row in service.db.query(AnalyticsStudentVideoProgress):
        row.evidence_json = {**row.evidence_json, 'playback_measurement': {
            'complete_history': True, 'unknown_intervals': 0, 'observed_intervals': 3,
            'media_seconds': 900, 'wall_seconds': 900, 'resume_continuity_checked': True}}
    service.db.commit()
    assert recalculate(service).classification != 'POSSIBLE_ANOMALY'


def test_incomplete_cumulative_history_does_not_use_a_recent_short_segment_as_total_watch():
    evidence = {'segments': [{'start': '2026-10-01', 'end': '2026-10-02', 'seconds': 1}],
        'playback_measurement': {'complete_history': False, 'unknown_intervals': 0, 'observed_intervals': 3}}
    assert not has_observed_watch_timing(evidence)


def test_resuming_near_the_end_does_not_prove_total_watch_was_near_zero(service):
    seed_videos(service)
    for row in service.db.query(AnalyticsStudentVideoProgress):
        row.evidence_json = {'event_count': 6, 'segments': [{
            'start': '2026-10-01T00:00:00', 'end': '2026-10-01T00:00:01', 'seconds': 1,
            'start_position_seconds': 998, 'end_position_seconds': 999}]}
    service.db.commit()
    assert recalculate(service).classification == 'INSUFFICIENT_DATA'


def paused_jump_events(resume_position=999):
    start = datetime(2026, 10, 1)
    return [VideoEventInput(event, start + timedelta(seconds=seconds), position, 1000)
            for event, seconds, position in [
                ('play_video', 0, 0), ('pause_video', 1, 1),
                ('play_video', 999, resume_position), ('pause_video', 1000, resume_position + 1)]]


@pytest.mark.parametrize('incremental', [False, True])
def test_unexplained_forward_position_jump_while_paused_marks_history_incomplete(incremental):
    events = paused_jump_events()
    measurement = (measure_playback(events[2:], previous=measure_playback(events[:2]))
                   if incremental else measure_playback(events))
    assert measurement['media_seconds'] == 2
    assert measurement['complete_history'] is False
    assert measurement['unknown_intervals'] >= 1


def test_resuming_at_the_same_position_preserves_complete_history():
    measurement = measure_playback(paused_jump_events(resume_position=1))
    assert measurement['complete_history'] is True
    assert measurement['unknown_intervals'] == 0


@pytest.mark.parametrize('cumulative', [False, True])
def test_unexplained_paused_position_jump_does_not_trigger_repeated_review(service, cumulative):
    seed_videos(service)
    events = paused_jump_events()
    calculated = calculate_video_progress(events)
    evidence = calculated.evidence
    if cumulative:
        evidence = {**evidence, 'playback_measurement': measure_playback(events)}
    for row in service.db.query(AnalyticsStudentVideoProgress):
        row.evidence_json = evidence
    service.db.commit()
    assert recalculate(service).classification == 'INSUFFICIENT_DATA'


def test_old_aggregate_complete_flag_without_continuity_check_is_insufficient(service):
    seed_videos(service)
    for row in service.db.query(AnalyticsStudentVideoProgress):
        row.evidence_json = {'event_count': 6, 'playback_measurement': {
            'version': 'video_playback_v1', 'complete_history': True,
            'unknown_intervals': 0, 'observed_intervals': 2, 'media_seconds': 2}}
    service.db.commit()
    row = recalculate(service)
    assert row.classification == 'INSUFFICIENT_DATA'
    assert row.data_quality == 'LOW'


def test_new_tail_cannot_retroactively_validate_old_unchecked_resume_history():
    events = paused_jump_events()
    old = measure_playback(events[:2])
    old.pop('resume_continuity_checked', None)
    result = measure_playback([], previous=old, historical_data=True)
    assert result['resume_continuity_checked'] is False


def test_fresh_explicit_seek_history_is_checked_and_still_supports_review():
    start = datetime(2026, 10, 1)
    events = [VideoEventInput(event, start + timedelta(seconds=second), position, 1000)
              for event, second, position in [('play_video', 0, 0), ('seek_video', 1, 999), ('pause_video', 2, 1000)]]
    result = calculate_video_progress(events)
    measurement = measure_playback(events)
    assert measurement['resume_continuity_checked'] is True
    assert has_observed_watch_timing({**result.evidence, 'playback_measurement': measurement})


def test_old_scoring_snapshot_requires_recompute_without_mutating_it():
    row = SimpleNamespace(calculated_at=datetime.utcnow(), reason_codes=['DEADLINE_PATTERN_MATCHED'],
        evidence_json={'scoring_version': 'learning_behavior_audit_v2'})
    result = behavior_freshness(row, stale_hours=24)
    assert result['snapshot_stale']
    assert result['snapshot_recompute_required']
    assert 'BEHAVIOR_RULES_UPDATED' in result['reason_codes']
    assert row.reason_codes == ['DEADLINE_PATTERN_MATCHED']
