import importlib
from datetime import datetime, timedelta


def fixture_items():
    items = []
    for user in ['a', 'b', *[f'ref{i}' for i in range(30)]]:
        for i in range(8):
            suspect = user in {'a', 'b'}
            items.append({
                'username': user, 'unit_usage_key': 'unit', 'problem_usage_key': f'q{i}',
                'input_slot': '_2_1', 'variant': '', 'content_version': 'v1',
                'question_hash': f'h{i}', 'response_type': 'multiplechoiceresponse',
                'answer_json': 'wrong' if suspect and i < 3 else 'right',
                'correct': not (suspect and i < 3), 'reveal_requested_before': False,
                'submitted_at': datetime(2026, 10, 5) + timedelta(seconds=i * 40 + (2 if user == 'b' else 0)),
            })
    return items


def run(items, context=None, config=None):
    module = importlib.import_module('app.services.learning_analytics.quiz_integrity_rules')
    return module.evaluate_quiz_integrity(items, context or [], config or {})


def test_rare_wrong_and_timing_require_all_gates():
    results = run(fixture_items())
    a = next(r for r in results if r['username'] == 'a')
    assert a['status'] == 'REVIEW_REQUIRED'
    assert a['evidence']['pairs'][0]['rare_wrong_count'] == 3
    assert a['evidence']['pairs'][0]['overlap_questions'] == 8


def test_small_cohort_and_other_variants():
    items = fixture_items()
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items[:16]))
    for item in items:
        if item['username'] == 'b':
            item['variant'] = 'different'
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items))


def test_burst_timing_does_not_escalate():
    items = fixture_items()
    for i, item in enumerate(items):
        item['submitted_at'] = datetime(2026, 10, 5) + timedelta(seconds=(i % 8) * .2)
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items))


def test_reset_policy_and_showanswer_request():
    context = [{'username': 'a', 'unit_usage_key': 'unit', 'reset_times': [
        '2026-10-05T00:00:00', '2026-10-05T00:01:00', '2026-10-05T00:02:00',
    ], 'answer_reveal_requests': [{'problem_usage_key': 'q', 'requested_at': '2026-10-05T00:00:00'}]}]
    assert run([], context)[0]['status'] != 'REVIEW_REQUIRED'
    assert run([], context, {'reset_policy': 'restricted'})[0]['status'] == 'REVIEW_REQUIRED'


def test_unknown_version_and_correctness_are_missing_data():
    items = fixture_items()
    for item in items:
        item['content_version'] = None
        item['correct'] = None
    assert all(r['status'] == 'INSUFFICIENT_DATA' for r in run(items))


def test_pair_cap_is_partial_and_resumable():
    result = run(fixture_items(), config={'pair_limit': 0})
    assert all(r['evidence']['partial'] for r in result)
    assert all(r['status'] == 'INSUFFICIENT_DATA' for r in result)
    assert run(fixture_items(), config={'pair_limit': 1})[0]['evidence']['partial'] is False


def test_burst_uses_unsupported_answers_as_timing_context():
    items = fixture_items()
    for item in items:
        i = int(item['problem_usage_key'][1:])
        item['submitted_at'] = datetime(2026, 10, 5) + timedelta(seconds=(i // 4) * 100 + i % 4)
    for user in ('a', 'b'):
        template = next(i for i in items if i['username'] == user)
        for burst in range(2):
            items.append({**template, 'problem_usage_key': f'text{burst}', 'response_type': 'stringresponse',
                          'submitted_at': datetime(2026, 10, 5) + timedelta(seconds=burst * 100 + 4)})
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items))


def test_burst_uses_server_submission_context_without_answer_metadata():
    items = fixture_items()
    for item in items:
        i = int(item['problem_usage_key'][1:])
        item['submitted_at'] = datetime(2026, 10, 5) + timedelta(seconds=(i // 4) * 100 + i % 4)
    contexts = [{'username': user, 'unit_usage_key': 'unit', 'server_submission_times': [
        {'problem_usage_key': f'unknown{burst}', 'submitted_at':
         (datetime(2026, 10, 5) + timedelta(seconds=burst * 100 + 4)).isoformat()}
        for burst in range(2)]} for user in ('a', 'b')]
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items, contexts))


def test_late_reveal_context_invalidates_durable_answer_and_resume_cache():
    items = fixture_items()
    before = run(items)
    contexts = [{'username': 'a', 'unit_usage_key': 'unit', 'answer_reveal_requests': [
        {'problem_usage_key': 'q0', 'requested_at': '2026-10-04T23:59:00'}]}]
    config = {'cursor': 1, 'fingerprint': before[0]['evidence']['fingerprint'],
              'previous_pairs': {(r['username'], 'unit'): r['evidence']['pairs'] for r in before}}
    assert all(r['status'] != 'REVIEW_REQUIRED' for r in run(items, contexts, config))
