from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicClass, AcademicClassStudent, AcademicStudent, AcademicQuizDeadlineOverride
from app.models.learning_analytics import (AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentVideoProgress, AnalyticsStudentSessionProgress)
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
from app.services.learning_analytics.learning_behavior_classifier import BehaviorInput, classify_learning_behavior


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    for model in (AcademicClass, AcademicQuizDeadlineOverride, AnalyticsCourseSession,
                  AcademicClassStudent, AcademicStudent, AnalyticsLearningBehaviorSnapshot,
                  AnalyticsStudentVideoProgress, AnalyticsStudentSessionProgress):
        model.__table__.create(engine)
    with Session(engine) as session:
        for name, month, day in [('september', 9, 15), ('november', 11, 6)]:
            session.add(AcademicClass(id=name, term_id='term', subject_id='subject',
                                     class_code=name, start_date=datetime(2026, month, day)))
        session.add(AnalyticsCourseSession(course_id='course', session_key='lesson',
                    session_index=1, session_title='Bài 1', week_index=1,
                    deadline_at=datetime(2026, 11, 12, 23, 59, 59),
                    deadline_source='INFERRED', deadline_mapping_quality='GOOD', active=True,
                    components_json={'components': [{'usage_key': 'quiz', 'block_type': 'problem', 'title': 'Quiz 1'}]}))
        session.commit()
        yield session
    engine.dispose()


def test_shared_course_inferred_deadline_is_resolved_for_each_class_without_mutation(db):
    service = LearningAnalyticsCoreService(db)
    september = service.get_session_structure(course_id='course', class_id='september')[0]
    november = service.get_session_structure(course_id='course', class_id='november')[0]
    assert september['deadline_at'] == '2026-09-21T23:59:59'
    assert november['deadline_at'] == '2026-11-12T23:59:59'
    assert september['deadline_mapping_quality'] == 'PARTIAL'
    assert september['components'][0]['deadline_at'] == '2026-09-21T23:59:59'
    assert db.query(AnalyticsCourseSession).one().deadline_at.month == 11


def test_explicit_quiz_deadline_wins_over_class_inference(db):
    db.add(AcademicQuizDeadlineOverride(class_id='september', course_id='course',
           quiz_number=1, deadline_date=datetime(2026, 9, 19, 12)))
    db.commit()
    result = LearningAnalyticsCoreService(db).get_session_structure(course_id='course', class_id='september')[0]
    assert result['deadline_at'] == '2026-09-19T12:00:00'
    assert result['deadline_source'] == 'QUIZ_DEADLINE'


def test_unknown_class_anchor_does_not_reuse_another_class_inferred_date(db):
    result = LearningAnalyticsCoreService(db).get_session_structure(course_id='course', class_id='missing')[0]
    assert result['deadline_at'] is None
    assert result['deadline_mapping_quality'] == 'LOW'


def test_no_video_cannot_award_watch_then_quiz_or_real_learning_points():
    result = classify_learning_behavior(BehaviorInput(
        total_sessions=8, sessions_started=8, total_quiz_sessions=8,
        video_before_quiz_count=8, sessions_completed_on_time=8,
        extra_reasons=['WATCH_THEN_ATTEMPT_PROBLEM']))
    assert 'WATCH_THEN_ATTEMPT_PROBLEM' not in result.reason_codes
    assert result.real_learning_score == 0
    assert result.classification == 'INSUFFICIENT_DATA'


def test_repeated_high_completion_low_watch_gets_teacher_review_without_quiz_signals():
    result = classify_learning_behavior(BehaviorInput(
        total_events=429, total_sessions=11, sessions_started=11,
        total_videos_seen=26, total_videos_completed=25,
        avg_video_completion_percent=97.28, avg_estimated_watch_percent=.24,
        avg_video_quality_percent=0, suspicious_video_count=25,
        extra_reasons=['HIGH_COMPLETION_LOW_WATCH_TIME', 'LARGE_SEEK_JUMP']))
    assert result.classification == 'POSSIBLE_ANOMALY'
    assert result.recommended_action == 'TEACHER_REVIEW'


@pytest.mark.parametrize('changes', [
    {'total_videos_seen': 1, 'total_videos_completed': 1, 'sessions_started': 1},
    {'missing_duration_count': 3},
    {'avg_estimated_watch_percent': 80},
    {'avg_video_completion_percent': 20},
])
def test_video_review_requires_repeated_complete_and_measurable_evidence(changes):
    values = dict(total_events=50, total_sessions=3, sessions_started=3,
                  total_videos_seen=3, total_videos_completed=3,
                  avg_video_completion_percent=97, avg_estimated_watch_percent=1,
                  suspicious_video_count=3)
    values.update(changes)
    assert classify_learning_behavior(BehaviorInput(**values)).classification != 'POSSIBLE_ANOMALY'


def seed_fresh_and_stale_students(db):
    for name, days in [('old', 10), ('fresh', 0)]:
        db.add(AcademicStudent(id=name, username=name, student_code=name, active=True))
        db.add(AcademicClassStudent(class_id='september', student_id=name))
        db.add(AnalyticsLearningBehaviorSnapshot(class_id='september', course_id='course',
            username=name, classification='NORMAL', confidence_score=90, data_quality='GOOD',
            calculated_at=datetime.utcnow() - timedelta(days=days)))
    db.commit()


def test_one_fresh_student_does_not_hide_other_stale_snapshots(db, monkeypatch):
    seed_fresh_and_stale_students(db)
    service = LearningAnalyticsCoreService(db)
    from app.services.learning_analytics.results import LearningAnalyticsResultsWorkflowService
    monkeypatch.setattr(LearningAnalyticsResultsWorkflowService, 'class_result_doctor', lambda *args, **kwargs: {})
    result = service.behavior_summary(class_id='september', course_id='course')
    assert result['stale_snapshot_count'] == 1
    assert result['data_status'] == 'partial'


def test_stale_behavior_is_identified_in_student_rows(db, monkeypatch):
    seed_fresh_and_stale_students(db)
    service = LearningAnalyticsCoreService(db)
    from app.services.learning_analytics.results import LearningAnalyticsResultsWorkflowService
    monkeypatch.setattr(LearningAnalyticsResultsWorkflowService, 'class_result_doctor', lambda *args, **kwargs: {})
    result = service.behavior_rows(class_id='september', course_id='course')
    old = next(row for row in result['items'] if row['username'] == 'old')
    fresh = next(row for row in result['items'] if row['username'] == 'fresh')
    assert old['snapshot_stale']
    assert 'STALE_BEHAVIOR_SNAPSHOT' in old['reason_codes']
    assert not fresh['snapshot_stale']


def test_quiz_snapshot_timestamps_use_same_utc_clock_as_tracking_logs():
    assert LearningAnalyticsCoreService._as_datetime('2026-10-07T16:00:00+07:00') == datetime(2026, 10, 7, 9)


def test_first_play_marker_and_post_submit_watch_do_not_prove_pre_quiz_watch():
    from types import SimpleNamespace
    row = SimpleNamespace(evidence_json={'segments': [
        {'start': '2026-10-07T09:10:00', 'end': '2026-10-07T09:20:00', 'seconds': 600}]})
    service = LearningAnalyticsCoreService
    assert service._observed_watch_before([row], datetime(2026, 10, 7, 9, 5)) == 0
    assert service._observed_watch_before([row], datetime(2026, 10, 7, 9, 25)) == 600


def test_shared_student_session_read_uses_requested_class_deadline_without_writing(db):
    row = AnalyticsStudentSessionProgress(course_id='course', username='student',
        session_key='lesson', session_index=1, total_videos=1, videos_seen=1, videos_completed=1,
        deadline_at=datetime(2026, 11, 12, 23, 59, 59), completed_before_deadline=True,
        completed_late=False, session_learning_status='LIKELY_COMPLETED',
        last_activity_at=datetime(2026, 10, 1), reason_codes=['DEADLINE_PATTERN_MATCHED', 'WATCH_THEN_ATTEMPT_PROBLEM'])
    db.add(row)
    db.commit()
    service = LearningAnalyticsCoreService(db)
    structure = service.get_session_structure(course_id='course', class_id='september')
    projected = service._session_progress_for_class([row], structure, 'september')[0]
    assert projected.deadline_at.month == 9
    assert projected.completed_late and projected.session_learning_status == 'COMPLETED_LATE'
    assert 'DEADLINE_PATTERN_MATCHED' not in projected.reason_codes
    assert 'WATCH_THEN_ATTEMPT_PROBLEM' not in projected.reason_codes
    assert row.deadline_at.month == 11 and not row.completed_late
    assert not db.dirty


def test_repeated_play_does_not_discard_an_already_observed_watch_segment():
    from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress
    start = datetime(2026, 10, 7)
    result = calculate_video_progress([
        VideoEventInput('play_video', start, 0, 300),
        VideoEventInput('edx.video.played', start + timedelta(seconds=120), 120, 300),
        VideoEventInput('pause_video', start + timedelta(seconds=121), 121, 300)])
    assert result.estimated_watch_seconds == 121


def test_repeated_play_does_not_split_a_long_passive_segment_to_bypass_its_cap():
    from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress
    start = datetime(2026, 10, 7)
    result = calculate_video_progress([
        VideoEventInput('play_video', start, 0, 1800),
        VideoEventInput('edx.video.played', start + timedelta(seconds=600), 600, 1800),
        VideoEventInput('pause_video', start + timedelta(seconds=1200), 1200, 1800)])
    assert result.long_passive_segment_count == 1
    assert result.estimated_watch_seconds == 600


def test_whole_quiz_official_snapshot_score_wins_over_one_retained_problem(db, monkeypatch):
    from types import SimpleNamespace
    from app.models.academic import AcademicStudentLearningSnapshot
    AcademicStudentLearningSnapshot.__table__.create(db.get_bind())
    snapshot = AcademicStudentLearningSnapshot(class_id='september', student_id='student',
        openedx_course_id='course', grade_percent=42, raw_json={'payload': {
            'component_scores': [{'name': 'Quiz 1', 'percent': 50}]}})
    db.add(snapshot)
    db.commit()
    service = LearningAnalyticsCoreService(db)
    partial = SimpleNamespace(id='partial', submission_count=1, started_at=datetime(2026, 9, 20),
        first_submission_at=datetime(2026, 9, 20), score_earned=1, score_possible=1,
        suspicious_quiz_speed=False, fishing_pattern=False, showanswer_count=0)
    monkeypatch.setattr(service, 'recalculate_course_quiz_attempts', lambda **kwargs: {})
    monkeypatch.setattr(service, '_student_usernames_for_class', lambda **kwargs: ['student'])
    monkeypatch.setattr(service, '_learning_snapshots_by_username', lambda **kwargs: {'student': snapshot})
    monkeypatch.setattr(service, '_quiz_attempts_for_user', lambda **kwargs: [partial])
    monkeypatch.setattr(service, '_resolve_quiz_attempts_by_session', lambda **kwargs: ({1: partial}, {}))
    service.recalculate_student_session_progress(class_id='september', course_id='course')
    result = db.query(AnalyticsStudentSessionProgress).one()
    assert result.quiz_score == 5
    assert result.evidence_json['quiz_score_source'] == 'OFFICIAL_COMPONENT_SNAPSHOT'
    assert snapshot.grade_percent == 42
    assert 'WATCH_THEN_ATTEMPT_PROBLEM' not in result.reason_codes
