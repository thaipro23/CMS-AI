"""Conservative, explainable tracking-log rules. No AI/tool attribution."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from statistics import median

RULE_VERSION = 'tracking_rules_v1'
CHOICE_TYPES = {'choiceresponse', 'multiplechoiceresponse', 'optionresponse'}


def _time(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _answer(item):
    return json.dumps(item['answer_json'], sort_keys=True, ensure_ascii=False)


def _key(item):
    return (item['unit_usage_key'], item['problem_usage_key'], item['input_slot'],
            item['variant'], item['content_version'], item['question_hash'])


def _burst_times(rows):
    times = defaultdict(set)
    for row in rows:
        times[_time(row['submitted_at'])].add(row['problem_usage_key'])
    points = sorted(times)
    burst = set()
    for origin in points:
        window = [t for t in points if 0 <= (t - origin).total_seconds() <= 10]
        if len(set().union(*(times[t] for t in window))) >= 5:
            burst.update(window)
    return burst


def evaluate_quiz_integrity(items: list[dict], context_events: list[dict], config: dict) -> list[dict]:
    """Return one class-scoped result per learner/unit, with resumable pair work.

    Items supplied by the caller already share a course and authorized class.
    Only supported server response metadata with a known version is compared.
    """
    users = defaultdict(dict)
    population = defaultdict(dict)
    all_by_user = defaultdict(list)
    contexts = defaultdict(list)
    reveals = defaultdict(dict)
    timing_context = defaultdict(list)
    for context in context_events:
        identity = (context['username'], context['unit_usage_key'])
        contexts[identity].append(context)
        timing_context[identity].extend(context.get('server_submission_times', []))
        for request in context.get('answer_reveal_requests', []):
            problem = request['problem_usage_key']
            when = _time(request['requested_at'])
            reveals[identity][problem] = min(when, reveals[identity].get(problem, when))
    for item in sorted(items, key=lambda row: _time(row['submitted_at'])):
        user_key = (item['username'], item['unit_usage_key'])
        all_by_user[user_key].append(item)
        if (not item.get('content_version') or type(item.get('correct')) is not bool
                or item.get('response_type') not in CHOICE_TYPES
                or item.get('answer_json') is None or item.get('reveal_requested_before')
                or (item['problem_usage_key'] in reveals[user_key]
                    and reveals[user_key][item['problem_usage_key']] <= _time(item['submitted_at']))):
            continue
        key = _key(item)
        users[user_key].setdefault(key, item)
        population[key].setdefault(item['username'], item)
    identities = sorted(set(contexts) | set(all_by_user))
    buckets = defaultdict(list)
    # Index rare wrong choices, rather than pairing the full class quadratically.
    for key, respondents in population.items():
        for username, item in respondents.items():
            if item['correct'] is False:
                buckets[(key, _answer(item))].append(username)
    candidates = set()
    for (key, answer), names in buckets.items():
        respondents = population[key]
        if len(names) < 2 or len(respondents) - 2 < 30:
            continue
        if (len(names) - 2) / (len(respondents) - 2) > .10:
            continue
        for a, b in combinations(sorted(set(names)), 2):
            candidates.add((key[0], a, b))
    ordered = sorted(candidates)
    fingerprint = hashlib.sha256(json.dumps({'items': [
        (i['username'], _key(i), _answer(i), str(i['submitted_at']), i.get('correct'),
         i.get('reveal_requested_before')) for i in items
    ], 'contexts': context_events, 'reset_policies': config.get('reset_policies'),
        'reset_policy': config.get('reset_policy')}, sort_keys=True, default=str).encode()).hexdigest()
    cursor = int(config.get('cursor') or 0) if config.get('fingerprint') == fingerprint else 0
    limit = max(0, min(10000, int(config.get('pair_limit', 10000))))
    batch = ordered[cursor:cursor + limit]
    next_cursor = cursor + len(batch)
    partial = next_cursor < len(ordered)
    pair_evidence = defaultdict(list)
    for unit, a, b in batch:
        left, right = users[(a, unit)], users[(b, unit)]
        common = set(left) & set(right)
        overlap = len({k[1] for k in common})
        if overlap < 8:
            continue
        matches = [k for k in common if _answer(left[k]) == _answer(right[k])]
        if len(matches) / len(common) < .8:
            continue
        rare = []
        for key in matches:
            if left[key]['correct'] is not False or right[key]['correct'] is not False:
                continue
            refs = [row for name, row in population[key].items() if name not in {a, b}]
            if len(refs) >= 30 and sum(_answer(r) == _answer(left[key]) for r in refs) / len(refs) <= .1:
                rare.append(key)
        if len({key[1] for key in rare}) < 3:
            continue
        burst_a = _burst_times([*all_by_user[(a, unit)], *timing_context[(a, unit)]])
        burst_b = _burst_times([*all_by_user[(b, unit)], *timing_context[(b, unit)]])
        timing = [key for key in sorted(common)
                  if _time(left[key]['submitted_at']) not in burst_a
                  and _time(right[key]['submitted_at']) not in burst_b]
        # Several inputs in one problem are one timestamp observation.
        timing = list({key[1]: key for key in timing}.values())
        if len(timing) < 6:
            continue
        gaps = [(_time(right[k]['submitted_at']) - _time(left[k]['submitted_at'])).total_seconds() for k in timing]
        lag = median(gaps)
        mad = median(abs(g - lag) for g in gaps)
        if abs(lag) > 300 or mad > 5 or max(sum(g >= 0 for g in gaps), sum(g <= 0 for g in gaps)) < .8 * len(gaps):
            continue
        proof = {
            'a_username': a, 'b_username': b,
            'overlap_questions': overlap, 'answer_similarity_percent': round(100 * len(matches) / len(common), 1),
            'rare_wrong_count': len({k[1] for k in rare}), 'timing_questions': len(timing),
            'median_lag_seconds': lag, 'lag_mad_seconds': mad,
            'questions': [{'problem_usage_key': k[1], 'input_slot': k[2],
                           'answer': left[k]['answer_json'], 'correct': left[k]['correct'],
                           'a_submitted_at': _time(left[k]['submitted_at']).isoformat(),
                           'b_submitted_at': _time(right[k]['submitted_at']).isoformat()}
                          for k in sorted(matches)[:30]],
        }
        pair_evidence[(a, unit)].append({**proof, 'other_username': b})
        pair_evidence[(b, unit)].append({**proof, 'other_username': a})
    results = []
    for identity in identities:
        username, unit = identity
        context = contexts[identity]
        reset_times = sorted({_time(t) for c in context for t in c.get('reset_times', [])})
        reset_burst = any(sum(0 <= (t - origin).total_seconds() <= 600 for t in reset_times) >= 3
                          for origin in reset_times)
        policy = (config.get('reset_policies') or {}).get(unit, config.get('reset_policy', 'unknown'))
        pairs = pair_evidence[identity]
        if cursor:
            pairs = [*((config.get('previous_pairs') or {}).get(identity, [])), *pairs]
        pairs = list({p['other_username']: p for p in pairs}.values())
        valid = users[identity]
        enough = len({k[1] for k in valid}) >= 8 and sum(len(population[k]) >= 32 for k in valid) >= 8
        review = bool(pairs or (reset_burst and policy == 'restricted'))
        status = 'REVIEW_REQUIRED' if review else 'NORMAL' if enough and not partial else 'INSUFFICIENT_DATA'
        reasons = []
        if pairs:
            reasons.append('RARE_WRONG_ANSWER_TIMING_MATCH')
        if reset_burst:
            reasons.append('REPEATED_RESET_REQUESTS')
        if _burst_times([*all_by_user[identity], *timing_context[identity]]):
            reasons.append('RAPID_SUBMISSION_BURST_CONTEXT')
        results.append({
            'username': username, 'unit_usage_key': unit, 'status': status, 'rule_version': RULE_VERSION,
            'evidence': {'reason_codes': reasons, 'pairs': pairs, 'partial': partial,
                         'cursor': next_cursor if partial else 0, 'fingerprint': fingerprint,
                         'reset_policy': policy, 'reset_request_count': len(reset_times),
                         'answer_reveal_request_count': sum(len(c.get('answer_reveal_requests', [])) for c in context),
                         'comparable_questions': len({k[1] for k in valid}),
                         'missing_baseline_or_version': not enough,
                         'rules': {'overlap_min': 8, 'similarity_min_percent': 80, 'rare_wrong_min': 3,
                                   'reference_people_min': 30, 'rare_max_percent': 10,
                                   'timing_min': 6, 'lag_max_seconds': 300, 'lag_mad_max_seconds': 5}},
        })
    return results
