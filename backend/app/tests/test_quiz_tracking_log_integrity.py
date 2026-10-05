from datetime import datetime, timedelta

from app.services.learning_analytics.quiz_attempt_analyzer import (
    EventLike, QUIZ_SESSION_START, build_quiz_attempt_features,
)

UNIT = 'block-v1:FPS+COM1091+FA26+type@vertical+block@u'
START = datetime(2026, 10, 5)


def event(kind, seconds, payload=None, source='server'):
    return EventLike(kind, source, START + timedelta(seconds=seconds), '1', 'sv',
                     'course-v1:FPS+COM1091+FA26', UNIT, payload or {}, {},
                     {'event_source': source})


def submit(seconds, problem='q1', earned=1, kind='edx.grades.problem.submitted'):
    return event(kind, seconds, {'problem_id': problem, 'grade': earned, 'max_grade': 1})


def test_itembank_result_and_added_are_read():
    result = build_quiz_attempt_features([event('edx.itembankblock.content.assigned', 0, {
        'location': 'bank', 'result': [{'usage_key': 'q1'}, {'usage_key': 'q2'}],
        'added': [{'usage_key': 'q1'}, {'usage_key': 'q2'}],
    })])[0]
    assert result.assigned_problem_usage_keys == ['q1', 'q2']


def test_grade_pair_not_double_counted():
    result = build_quiz_attempt_features([submit(10, kind='problem_check'), submit(10.1)])[0]
    assert len(result.submissions) == 1
    assert (result.score_earned, result.score_possible) == (1, 1)


def test_retry_score_uses_latest_per_problem_and_keeps_fallback():
    result = build_quiz_attempt_features([
        submit(10, earned=0), submit(40), submit(50, 'q2', kind='problem_check'),
    ])[0]
    assert len(result.submissions) == 3
    assert (result.score_earned, result.score_possible) == (2, 2)


def test_missing_start_is_explicit():
    result = build_quiz_attempt_features([submit(10)])[0]
    assert result.low_confidence_reason == 'MISSING_QUIZ_SESSION_START'
    assert result.evidence['duration_seconds'] is None


def test_explicit_start_has_attempt_duration():
    result = build_quiz_attempt_features([
        event(QUIZ_SESSION_START, 0, {'unit_usage_key': UNIT}), submit(205),
    ])[0]
    assert result.evidence['duration_seconds'] == 205
    assert result.evidence['duration_source'] == 'START_REQUEST_TO_LAST_SUBMISSION'


def test_submit_burst_is_context_only():
    result = build_quiz_attempt_features([submit(i * .3, f'q{i}') for i in range(15)])[0]
    assert result.suspicious_quiz_speed is False
    assert result.evidence['rapid_submission_burst'] is True


def test_showanswer_and_reset_requests_are_neutral():
    result = build_quiz_attempt_features([
        event('showanswer', 1, {'problem_id': 'q1'}), submit(2),
        event('/api/unit-reset/v1/quiz-session/reset', 3, {'unit_usage_key': UNIT}),
    ])[0]
    assert result.fishing_pattern is False
    assert result.evidence['answer_reveal_requests'][0]['problem_usage_key'] == 'q1'


def test_two_real_server_checks_are_not_collapsed_without_canonical():
    result = build_quiz_attempt_features([
        submit(10, earned=0, kind='problem_check'), submit(10.5, kind='problem_check'),
    ])[0]
    assert len(result.submissions) == 2
    assert result.score_earned == 1


def test_three_companion_event_types_are_one_submission():
    result = build_quiz_attempt_features([
        submit(10, kind='problem_check'), submit(10.1, kind='problem_graded'), submit(10.2),
    ])[0]
    assert len(result.submissions) == 1


def test_identical_delivery_is_deduplicated_but_actual_retry_is_retained():
    result = build_quiz_attempt_features([
        submit(10, kind='problem_check'), submit(10, kind='problem_check'),
        submit(10.5, kind='problem_check'),
    ])[0]
    assert len(result.submissions) == 2


def test_consecutive_reset_requests_are_all_retained():
    from app.services.learning_analytics.quiz_attempt_analyzer import QUIZ_SESSION_RESET
    from app.services.learning_analytics.quiz_integrity_rules import evaluate_quiz_integrity
    features = build_quiz_attempt_features([
        submit(10), *[event(QUIZ_SESSION_RESET, t, {'unit_usage_key': UNIT}) for t in (30, 60, 90)],
    ])
    contexts = [{'username': f.username, 'unit_usage_key': f.unit_usage_key, **f.evidence} for f in features]
    result = evaluate_quiz_integrity([], contexts, {'reset_policy': 'restricted'})[0]
    assert result['evidence']['reset_request_count'] == 3
    assert result['status'] == 'REVIEW_REQUIRED'
