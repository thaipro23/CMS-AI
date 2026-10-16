from datetime import datetime, timedelta, timezone
from importlib import import_module, util

import pytest

NOW = datetime(2026, 10, 9, 8)


@pytest.fixture
def ml():
    class Builders:
        def __getattr__(self, attr):
            name = 'app.services.learning_analytics.ml_features'
            assert util.find_spec(name), 'ML feature builders are not implemented'
            return getattr(import_module(name), attr)
    return Builders()


def video(**changes):
    return dict(video_id='v', duration_seconds=100, session_index=1,
                completion_percent=90, estimated_watch_seconds=70,
                passive_watch_seconds=20, seek_count=2, last_event_at=NOW,
                **changes)


def videos(n):
    return [dict(video(), video_id=f'v{i}') for i in range(n)]


def build_video(ml, rows):
    return ml.build_video_features(subject_key='u', course_id='course',
        outline_fingerprint='outline', videos=rows, cutoff=NOW)


def test_three_measurable_videos_required(ml):
    assert build_video(ml, videos(2)).row is None
    row = build_video(ml, videos(3)).row
    assert row.features['watch_ratio'] == pytest.approx(.7)
    assert row.features['completion_watch_gap'] == pytest.approx(.2)
    assert row.features['seeks_per_watch_minute'] == pytest.approx(12/7)
    assert row.features['passive_ratio'] == pytest.approx(2/7)


def test_missing_duration_not_zero(ml):
    rows = videos(3)
    rows[0]['duration_seconds'] = None
    result = build_video(ml, rows)
    assert result.row is None
    assert 'MISSING_VIDEO_DURATION' in result.reasons


@pytest.mark.parametrize('field,value', [('estimated_watch_seconds', None),
    ('estimated_watch_seconds', float('nan')), ('seek_count', -1),
    ('completion_percent', float('inf')), ('session_index', None),
    ('last_event_at', NOW + timedelta(days=1))])
def test_invalid_video_measurements_do_not_become_zero(ml, field, value):
    rows = videos(3)
    rows[0][field] = value
    assert build_video(ml, rows).row is None


def test_video_utc_and_exposure_cohort(ml):
    row = build_video(ml, videos(3)).row
    rows = videos(3)
    for v in rows:
        v['last_event_at'] = NOW.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
    assert build_video(ml, rows).row.features == row.features
    assert build_video(ml, videos(6)).row.cohort_key != row.cohort_key


def quiz():
    attempt = dict(started_at=NOW-timedelta(minutes=10), ended_at=NOW,
        unit_reset_nonce='quiz-session:1', reset_count=1, attempt_no=1,
        evidence_json={'start_observed': True, 'session_event_provenance': 'server_quiz_session_v1',
            'submission_timing_provenance':'server_submissions_v1',
            'reset_event_provenance':'server_reset_new_session_v1', 'successful_reset_times':[(NOW-timedelta(minutes=10)).isoformat()],
            'reset_times': [(NOW-timedelta(minutes=10)).isoformat()],
            'server_submission_times': []})
    items = [dict(problem_usage_key=f'p{i}', input_slot='_1_1', variant='',
        content_version='sha256:'+'a'*64, question_hash=f'{i:064x}',
        submitted_at=NOW-timedelta(minutes=9-i), unit_reset_nonce='quiz-session:1')
        for i in range(6)]
    attempt['evidence_json']['server_submission_times'] = [
        dict(problem_usage_key=x['problem_usage_key'], submitted_at=x['submitted_at'].isoformat())
        for x in items]
    return attempt, items


def build_quiz(ml, attempt, items):
    return ml.build_quiz_features(subject_key='u', course_id='course', unit_usage_key='quiz',
        attempt=attempt, items=items, cutoff=NOW)


def test_server_quiz_features_use_independent_times(ml):
    attempt, items = quiz()
    row = build_quiz(ml, attempt, items).row
    assert row is not None
    assert row.features['seconds_per_independent_submission'] == 60
    assert row.features['successful_resets_per_attempt'] == 1
    assert row.features['submissions_per_response'] == 1


def test_untrusted_start_and_missing_version_rejected(ml):
    attempt, items = quiz()
    attempt['evidence_json']['session_event_provenance'] = 'request_log'
    assert 'UNTRUSTED_QUIZ_SESSION' in build_quiz(ml, attempt, items).reasons
    attempt, items = quiz()
    items[0]['content_version'] = None
    assert 'MISSING_CONTENT_VERSION' in build_quiz(ml, attempt, items).reasons


def test_timeout_burst_excluded(ml):
    attempt, items = quiz()
    for x in items:
        x['submitted_at'] = NOW-timedelta(seconds=2)
    attempt['evidence_json']['server_submission_times'] = [dict(problem_usage_key=x['problem_usage_key'], submitted_at=x['submitted_at'].isoformat()) for x in items]
    assert 'INSUFFICIENT_INDEPENDENT_TIMING' in build_quiz(ml, attempt, items).reasons


def test_response_set_changes_cohort(ml):
    attempt, items = quiz()
    first = build_quiz(ml, attempt, items).row
    items[0]['content_version'] = 'sha256:'+'b'*64
    assert build_quiz(ml, attempt, items).row.cohort_key != first.cohort_key


def test_browser_item_timestamps_cannot_supply_independent_timing(ml):
    attempt, items = quiz()
    attempt['evidence_json']['server_submission_times'] = []
    assert build_quiz(ml, attempt, items).row is None


def test_cross_class_student_dedup(ml):
    row = build_video(ml, videos(3)).row
    assert len(ml.unique_reference_rows([row]*20)) == 1


def test_duplicate_video_rows_do_not_satisfy_three_video_gate(ml):
    assert build_video(ml, [video()]*3).row is None


def test_full_and_bare_block_ids_are_one_measured_video(ml):
    rows=videos(3)
    rows[1]['video_id']='block-v1:ORG+COURSE+RUN+type@video+block@v0'
    assert build_video(ml,rows).row is None


def test_legacy_timing_without_trusted_provenance_is_not_upgraded(ml):
    attempt,items=quiz()
    attempt['evidence_json'].pop('submission_timing_provenance',None)
    result=build_quiz(ml,attempt,items)
    assert result.row is None and 'UNTRUSTED_SUBMISSION_TIMING' in result.reasons
