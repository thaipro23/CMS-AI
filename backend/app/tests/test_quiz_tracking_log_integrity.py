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
        event(QUIZ_SESSION_START, 0, {'unit_usage_key': UNIT,
            'unit_reset_nonce': 'quiz-session:1', 'started_at': START.isoformat()}), submit(205),
    ])[0]
    assert result.evidence['duration_seconds'] == 205
    assert result.evidence['duration_source'] == 'START_REQUEST_TO_LAST_SUBMISSION'


def test_assignment_rendered_before_timer_start_belongs_to_that_attempt():
    results = build_quiz_attempt_features([
        event('edx.itembankblock.content.assigned', 0, {'result': [{'usage_key': 'q1'}]}),
        event(QUIZ_SESSION_START, 2, {'unit_usage_key': UNIT,
            'unit_reset_nonce': 'quiz-session:1', 'started_at': (START + timedelta(seconds=2)).isoformat()}),
        submit(100)])
    assert len(results) == 1
    assert results[0].assigned_problem_usage_keys == ['q1']
    assert results[0].attempt_no == 1
    assert results[0].evidence['duration_seconds'] == 98


def test_refresh_start_uses_server_session_time_without_splitting_same_attempt():
    payload = {'unit_usage_key': UNIT, 'unit_reset_nonce': 'quiz-session:42',
               'started_at': START.isoformat()}
    results = build_quiz_attempt_features([
        submit(100), event(QUIZ_SESSION_START, 110, payload),
        event(QUIZ_SESSION_START, 120, payload), submit(205)])
    assert len(results) == 1
    assert results[0].evidence['duration_seconds'] == 205
    assert len(results[0].submissions) == 2


def test_browser_supplied_start_time_is_not_authoritative():
    result = build_quiz_attempt_features([
        event(QUIZ_SESSION_START, 110, {'unit_usage_key': UNIT,
             'started_at': START.isoformat()}, source='browser'), submit(205)])[0]
    assert result.start_observed is False
    assert result.evidence['duration_seconds'] is None


def test_server_problem_scope_groups_dynamic_clone_and_companion_grade():
    clone = 'block-v1:FPS+COM1091+FA26+type@problem+block@random-clone'
    check = event('problem_check', 100, {'problem_id': clone, 'unit_usage_key': UNIT,
                                       'grade': 1, 'max_grade': 1})
    grade = event('edx.grades.problem.submitted', 100.1,
                  {'problem_id': clone, 'grade': 1, 'max_grade': 1})
    grade.page_url = clone
    results = build_quiz_attempt_features([check, grade])
    assert len(results) == 1
    assert results[0].unit_usage_key == UNIT
    assert len(results[0].submissions) == 1


def test_browser_problem_scope_cannot_reassign_companion_server_grade():
    clone = 'block-v1:FPS+COM1091+FA26+type@problem+block@random-clone'
    check = event('problem_check', 100, {'problem_id': clone, 'unit_usage_key': UNIT}, source='browser')
    grade = event('edx.grades.problem.submitted', 100.1,
                  {'problem_id': clone, 'grade': 1, 'max_grade': 1})
    grade.page_url = clone
    results = build_quiz_attempt_features([check, grade])
    assert next(row for row in results if row.unit_usage_key == clone).submissions[0]['event_source'] == 'server'


def test_new_server_session_after_reset_keeps_two_attempts_and_records_reset_request():
    first = {'unit_usage_key': UNIT, 'unit_reset_nonce': 'quiz-session:1', 'started_at': START.isoformat()}
    second = {'unit_usage_key': UNIT, 'unit_reset_nonce': 'quiz-session:2',
              'started_at': (START + timedelta(seconds=500)).isoformat(), 'reset_request': True}
    attempts = build_quiz_attempt_features([
        event(QUIZ_SESSION_START, 0, first), submit(100),
        event(QUIZ_SESSION_START, 501, second), submit(600)])
    assert len(attempts) == 2
    assert attempts[0].reset_count == 1
    assert [a.evidence['duration_seconds'] for a in attempts] == [100, 100]


def test_request_logs_cannot_split_a_successful_session_or_count_failed_resets():
    canonical = {'unit_usage_key': UNIT, 'unit_reset_nonce': 'quiz-session:1',
                 'started_at': START.isoformat()}
    attempts = build_quiz_attempt_features([
        event(QUIZ_SESSION_START, 1, canonical), submit(100),
        event(QUIZ_SESSION_START, 101, {'unit_usage_key': UNIT}),
        event('/api/unit-reset/v1/quiz-session/reset', 110, {'unit_usage_key': UNIT}),
        event('/api/unit-reset/v1/quiz-session/reset', 120, {'unit_usage_key': UNIT}, source='browser'),
        event(QUIZ_SESSION_START, 130, canonical), submit(200)])
    assert len(attempts) == 1
    assert attempts[0].reset_count == 0
    assert attempts[0].evidence['duration_seconds'] == 200


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


def test_consecutive_successful_server_resets_are_all_retained():
    from app.services.learning_analytics.quiz_integrity_rules import evaluate_quiz_integrity
    features = build_quiz_attempt_features([
        submit(10), *[event(QUIZ_SESSION_START, t, {'unit_usage_key': UNIT,
            'unit_reset_nonce': f'quiz-session:{t}', 'reset_request': True,
            'started_at': (START + timedelta(seconds=t)).isoformat()}) for t in (30, 60, 90)],
    ])
    contexts = [{'username': f.username, 'unit_usage_key': f.unit_usage_key, **f.evidence} for f in features]
    result = evaluate_quiz_integrity([], contexts, {'reset_policy': 'restricted'})[0]
    assert result['evidence']['reset_request_count'] == 3
    assert result['status'] == 'REVIEW_REQUIRED'
