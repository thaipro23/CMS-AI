import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace


def attempt(**kwargs):
    data = dict(id='a1', unit_usage_key='u1', attempt_no=1, started_at=datetime(2026, 10, 5),
                last_submission_at=datetime(2026, 10, 5) + timedelta(seconds=205),
                first_submission_at=datetime(2026, 10, 5) + timedelta(seconds=80),
                submission_count=15, reset_count=0, showanswer_count=0,
                score_earned=12, score_possible=15, evidence_json={})
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_duration_missing_start_is_not_zero():
    module = importlib.import_module('app.services.learning_analytics.quiz_detail')
    result = module.serialize_quiz_attempt(attempt(), 'Quiz 1')
    assert result['duration_seconds'] is None
    assert result['started_at'] is None


def test_start_request_duration_and_score_unchanged():
    module = importlib.import_module('app.services.learning_analytics.quiz_detail')
    row = attempt(evidence_json={'start_request_at': '2026-10-05T00:00:00'})
    result = module.serialize_quiz_attempt(row, 'Quiz 1')
    assert result['duration_seconds'] == 205
    assert result['score_earned'] == row.score_earned == 12
    assert result['score_possible'] == row.score_possible == 15


def test_pair_evidence_is_filtered_to_current_class_roster():
    module = importlib.import_module('app.services.learning_analytics.quiz_detail')
    evidence = {'pairs': [{'other_username': 'poly'}, {'other_username': 'ptcd'}], 'reset_request_count': 3}
    assert module.visible_pair_evidence(evidence, {'poly'})['pairs'] == [{'other_username': 'poly'}]
    assert len(evidence['pairs']) == 2
