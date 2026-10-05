from __future__ import annotations

import re
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

QUIZ_SESSION_START = '/api/unit-reset/v1/quiz-session/start'
QUIZ_SESSION_STATUS = '/api/unit-reset/v1/quiz-session/status'
QUIZ_SESSION_RESET = '/api/unit-reset/v1/quiz-session/reset'
SUBMIT_EVENTS = {'edx.grades.problem.submitted', 'problem_check', 'problem_graded'}
ITEMBANK_EVENTS = {'edx.itembankblock.content.assigned'}
SHOWANSWER_EVENTS = {'problem_show', 'showanswer'}


@dataclass(slots=True)
class QuizAttemptFeature:
    course_id: str
    username: str
    user_id: str | None
    sequence_usage_key: str | None
    unit_usage_key: str
    attempt_no: int
    unit_reset_nonce: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    reset_count: int = 0
    assigned_problem_usage_keys: list[str] = field(default_factory=list)
    itembank_locations: list[str] = field(default_factory=list)
    submissions: list[dict[str, Any]] = field(default_factory=list)
    showanswer_count: int = 0
    suspicious_quiz_speed: bool = False
    fishing_pattern: bool = False
    repeat_rate: float | None = None
    median_time_per_question_seconds: float | None = None
    score_earned: float | None = None
    score_possible: float | None = None
    low_confidence_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    start_observed: bool = False
    raw_submissions: list[dict[str, Any]] = field(default_factory=list)
    answer_reveal_requests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def first_submission_at(self) -> datetime | None:
        times = [s.get('submitted_at') for s in self.submissions if s.get('submitted_at')]
        return min(times) if times else None

    @property
    def last_submission_at(self) -> datetime | None:
        times = [s.get('submitted_at') for s in self.submissions if s.get('submitted_at')]
        return max(times) if times else None


@dataclass(slots=True)
class EventLike:
    event_type: str
    event_source: str | None
    event_time: datetime | None
    user_id: str | None
    username: str | None
    course_id: str | None
    page_url: str | None
    raw_event: dict[str, Any] | None
    raw_context: dict[str, Any] | None
    raw_json: dict[str, Any] | None
    raw_event_id: str | None = None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_scalar(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        for item in value:
            if item is not None and str(item).strip():
                return item
        return None
    return value


def _payload_param(payload: dict[str, Any], key: str) -> Any:
    value = _first_scalar(payload.get(key))
    if value is not None and str(value).strip():
        return value
    for bucket_name in ('GET', 'POST'):
        bucket = payload.get(bucket_name)
        if isinstance(bucket, dict):
            value = _first_scalar(bucket.get(key))
            if value is not None and str(value).strip():
                return value
    return None


def _vertical_usage_key(text: str | None) -> str | None:
    if not text:
        return None
    for match in re.finditer(r'block-v1:[^\s"\']+', text):
        candidate = re.split(r'[/?&#]', match.group(0), maxsplit=1)[0].rstrip(',')
        if '+type@vertical+block@' in candidate:
            return candidate
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == '':
            return None
        return float(value)
    except Exception:
        return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _walk_values(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            out.extend(_walk_values(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_walk_values(item))
    elif obj is not None:
        text = str(obj)
        if text:
            out.append(text)
    return out


def extract_usage_key(event: EventLike, *, prefer_problem: bool = False) -> str | None:
    payload = event.raw_event or {}
    context = event.raw_context or {}
    if prefer_problem:
        keys = ('problem_id', 'problem_usage_key', 'usage_key', 'item_usage_key', 'module_id', 'block_id')
        for key in keys:
            value = _safe_str(_payload_param(payload, key)) or _safe_str(context.get(key))
            if value:
                return value
    else:
        # Production quiz-session/status puts unit_usage_key in event.GET.
        for key in ('unit_usage_key', 'unit_key'):
            value = _safe_str(_payload_param(payload, key)) or _safe_str(context.get(key))
            if value:
                return value
        # Grade events expose problem_id, but their page/referer identifies the
        # vertical quiz unit. Group by that vertical rather than by each problem.
        vertical = _vertical_usage_key(event.page_url)
        if vertical:
            return vertical
        for key in ('usage_key', 'module_id', 'block_id', 'problem_id', 'problem_usage_key'):
            value = _safe_str(_payload_param(payload, key)) or _safe_str(context.get(key))
            if value:
                return value
    for text in [event.page_url or ''] + _walk_values(payload):
        match = re.search(r'block-v1:[^\s"\']+', text)
        if match:
            return match.group(0).rstrip('?/&,')
    return event.page_url or 'UNKNOWN_QUIZ_UNIT'

def extract_sequence_key(event: EventLike) -> str | None:
    payload = event.raw_event or {}
    context = event.raw_context or {}
    for key in ('sequence_usage_key', 'sequence_key', 'section_key'):
        value = _safe_str(_payload_param(payload, key)) or _safe_str(context.get(key))
        if value:
            return value
    return None


def extract_unit_reset_nonce(event: EventLike) -> str | None:
    payload = event.raw_event or {}
    for key in ('unit_reset_nonce', 'nonce', 'reset_nonce'):
        value = _safe_str(_payload_param(payload, key))
        if value:
            return value
    if event.page_url:
        match = re.search(r'unit_reset_nonce=([^&#]+)', event.page_url)
        if match:
            return match.group(1)
    return None


def _submission_score(event: EventLike) -> tuple[float | None, float | None]:
    payload = event.raw_event or {}
    earned = _first_float(
        payload.get('weighted_earned'),
        payload.get('grade'),
        payload.get('score'),
        payload.get('earned'),
    )
    possible = _first_float(
        payload.get('weighted_possible'),
        payload.get('max_grade'),
        payload.get('max_score'),
        payload.get('possible'),
    )
    return earned, possible


def source_of(event: EventLike) -> str:
    return str((event.raw_json or {}).get('event_source') or event.event_source or '').lower()


def deduplicate_submissions(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer canonical grades per action, retaining unmatched server checks.

    Each action may have one companion of each event type within two seconds.
    Same-type retries remain separate; identical transport deliveries collapse.
    """
    unique = {}
    for item in submissions:
        signature = json.dumps({k: v for k, v in item.items() if k != 'event_id'},
                               sort_keys=True, default=str)
        unique.setdefault(signature, item)
    ordered = sorted(unique.values(), key=lambda s: s.get('submitted_at') or datetime.min)
    canonical = [s for s in ordered if s['event_type'] == 'edx.grades.problem.submitted']
    fallback = [s for s in ordered if s['event_type'] != 'edx.grades.problem.submitted']
    matched: dict[int, set[str]] = defaultdict(set)
    fallback_types: dict[int, set[str]] = {}
    result = list(canonical)
    for item in fallback:
        if item.get('event_source') not in {'server', 'openedx_tracking_log'}:
            continue
        candidates = [
            (abs((other['submitted_at'] - item['submitted_at']).total_seconds()), i)
            for i, other in enumerate(canonical)
            if item['event_type'] not in matched[i] and other['problem_usage_key'] == item['problem_usage_key']
            and (not other.get('attempt_index') or not item.get('attempt_index')
                 or other['attempt_index'] == item['attempt_index'])
            and abs((other['submitted_at'] - item['submitted_at']).total_seconds()) <= 2
        ]
        if candidates:
            matched[min(candidates)[1]].add(item['event_type'])
        else:
            # problem_graded may accompany the detailed problem_check as well.
            existing = next((s for s in result if s['problem_usage_key'] == item['problem_usage_key']
                             and s['event_type'] != 'edx.grades.problem.submitted'
                             and item['event_type'] not in fallback_types.get(id(s), {s['event_type']})
                             and abs((s['submitted_at'] - item['submitted_at']).total_seconds()) <= 2
                             and s.get('attempt_index') == item.get('attempt_index')), None)
            if existing is None:
                result.append(item)
                fallback_types[id(item)] = {item['event_type']}
            else:
                fallback_types[id(existing)].add(item['event_type'])
    return sorted(result, key=lambda s: s['submitted_at'])


def _finalize_attempt(feature: QuizAttemptFeature, reset_times: list[datetime]) -> None:
    # Open edX can emit browser problem_check, problem_graded and the canonical
    # edx.grades.problem.submitted for the same action. Prefer the canonical
    # server grade events when present; keep legacy/browser rows only as fallback.
    all_submissions = list(feature.submissions)
    feature.raw_submissions = all_submissions
    canonical_submissions = [s for s in all_submissions if s['event_type'] == 'edx.grades.problem.submitted']
    fallback_submission_count = len(all_submissions) - len(canonical_submissions)
    feature.submissions = deduplicate_submissions(all_submissions)
    latest = {}
    for submission in feature.submissions:
        latest[submission['problem_usage_key']] = submission
    scores = [s for s in latest.values() if s.get('earned') is not None and s.get('possible') is not None]
    feature.score_earned = sum(s['earned'] for s in scores) if scores else None
    feature.score_possible = sum(s['possible'] for s in scores) if scores else None

    submitted_times = [s['submitted_at'] for s in feature.submissions if s.get('submitted_at')]
    if submitted_times:
        feature.ended_at = max(submitted_times)
    elif feature.started_at:
        feature.ended_at = feature.started_at
    unique = list(dict.fromkeys(feature.assigned_problem_usage_keys))
    if feature.assigned_problem_usage_keys:
        repeated = len(feature.assigned_problem_usage_keys) - len(unique)
        feature.repeat_rate = round(repeated / max(1, len(feature.assigned_problem_usage_keys)), 4)
    deltas: list[float] = []
    ordered_submits = sorted(feature.submissions, key=lambda item: item.get('submitted_at') or datetime.min)
    previous = None
    for item in ordered_submits:
        current = item.get('submitted_at')
        if previous and current and current >= previous:
            deltas.append((current - previous).total_seconds())
        if current:
            previous = current
    if deltas:
        feature.median_time_per_question_seconds = round(float(median(deltas)), 2)
    # Auto-submit at timeout creates bursts; these are context only.
    feature.suspicious_quiz_speed = False
    feature.fishing_pattern = False
    rapid_burst = any(
        len({s['problem_usage_key'] for s in ordered_submits
             if 0 <= (s['submitted_at'] - origin['submitted_at']).total_seconds() <= 10}) >= 5
        for origin in ordered_submits
    )
    if not feature.start_observed and feature.submissions:
        feature.low_confidence_reason = 'MISSING_QUIZ_SESSION_START'
    duration = None
    if feature.start_observed and feature.started_at and feature.last_submission_at:
        duration = max(0.0, (feature.last_submission_at - feature.started_at).total_seconds())
    feature.evidence = {
        'rule_version': 'tracking_rules_v1',
        'start_observed': feature.start_observed,
        'duration_seconds': duration,
        'duration_source': 'START_REQUEST_TO_LAST_SUBMISSION' if duration is not None else 'UNKNOWN',
        'median_submission_gap_seconds': feature.median_time_per_question_seconds,
        'rapid_submission_burst': rapid_burst,
        'answer_reveal_requests': feature.answer_reveal_requests,
        'server_submission_times': [
            {'problem_usage_key': s['problem_usage_key'], 'submitted_at': s['submitted_at'].isoformat()}
            for s in feature.submissions
        ],
        'assigned_problem_count': len(feature.assigned_problem_usage_keys),
        'distinct_assigned_problem_count': len(unique),
        'submission_count': len(feature.submissions),
        'showanswer_count': feature.showanswer_count,
        'repeat_rate': feature.repeat_rate,
        'median_time_per_question_seconds': feature.median_time_per_question_seconds,
        'score_earned': feature.score_earned,
        'score_possible': feature.score_possible,
        'server_canonical_submission': bool(canonical_submissions),
        'fallback_submission_count': fallback_submission_count,
        'showanswer_policy': 'request_only_neutral',
        'reset_times': [d.isoformat() for d in reset_times[:20]],
    }


def build_quiz_attempt_features(events: list[EventLike]) -> list[QuizAttemptFeature]:
    by_user_unit: dict[tuple[str, str, str], list[EventLike]] = defaultdict(list)
    for ev in events:
        if not ev.course_id or not ev.username or not ev.user_id or not ev.event_time:
            # user_id null events are kept in raw store but never counted for personal behavior.
            continue
        unit_key = extract_usage_key(ev) or 'UNKNOWN_QUIZ_UNIT'
        by_user_unit[(ev.course_id, ev.username, unit_key)].append(ev)

    features: list[QuizAttemptFeature] = []
    for (course_id, username, unit_key), items in by_user_unit.items():
        ordered = sorted(items, key=lambda e: e.event_time or datetime.min)
        current: QuizAttemptFeature | None = None
        attempt_no = 0
        reset_times: list[datetime] = []
        closed_by_reset: QuizAttemptFeature | None = None

        def ensure_attempt(ev: EventLike) -> QuizAttemptFeature:
            nonlocal current, attempt_no
            if current is None:
                attempt_no += 1
                current = QuizAttemptFeature(
                    course_id=course_id,
                    username=username,
                    user_id=ev.user_id,
                    sequence_usage_key=extract_sequence_key(ev),
                    unit_usage_key=unit_key,
                    attempt_no=attempt_no,
                    started_at=ev.event_time,
                    unit_reset_nonce=extract_unit_reset_nonce(ev),
                )
            return current

        for ev in ordered:
            et = ev.event_type
            if et != QUIZ_SESSION_RESET:
                closed_by_reset = None
            if et == QUIZ_SESSION_START:
                if current and (current.submissions or current.assigned_problem_usage_keys or current.showanswer_count):
                    _finalize_attempt(current, reset_times)
                    features.append(current)
                    current = None
                    reset_times = []
                attempt_no += 1
                current = QuizAttemptFeature(
                    course_id=course_id,
                    username=username,
                    user_id=ev.user_id,
                    sequence_usage_key=extract_sequence_key(ev),
                    unit_usage_key=unit_key,
                    attempt_no=attempt_no,
                    started_at=ev.event_time,
                    unit_reset_nonce=extract_unit_reset_nonce(ev),
                    start_observed=True,
                )
                continue
            if et == QUIZ_SESSION_STATUS:
                # Production /start events have no course/unit payload. /status is
                # the first course-bound marker and carries course/sequence/unit in
                # event.GET, so use it to open the attempt when necessary.
                feat = ensure_attempt(ev)
                if feat.sequence_usage_key is None:
                    feat.sequence_usage_key = extract_sequence_key(ev)
                continue
            if et == QUIZ_SESSION_RESET:
                if ev.event_time:
                    reset_times.append(ev.event_time)
                if current is None and closed_by_reset is not None:
                    closed_by_reset.reset_count += 1
                    closed_by_reset.evidence['reset_times'] = [d.isoformat() for d in reset_times]
                    continue
                if current is None:
                    ensure_attempt(ev)
                if current:
                    current.reset_count += 1
                    _finalize_attempt(current, reset_times)
                    features.append(current)
                    closed_by_reset = current
                    current = None
                continue
            feat = ensure_attempt(ev)
            if et in ITEMBANK_EVENTS:
                payload = ev.raw_event or {}
                assigned = payload.get('result') or payload.get('added') or []
                for child in assigned if isinstance(assigned, list) else []:
                    key = child.get('usage_key') if isinstance(child, dict) else None
                    if key:
                        feat.assigned_problem_usage_keys.append(str(key))
                if not assigned:
                    key = payload.get('problem_usage_key') or payload.get('item_usage_key')
                    if key:
                        feat.assigned_problem_usage_keys.append(str(key))
                for candidate in ('location', 'itembank_location', 'library_key', 'block_id'):
                    val = _safe_str(payload.get(candidate))
                    if val:
                        feat.itembank_locations.append(val)
                continue
            if et in SUBMIT_EVENTS:
                actual_source = source_of(ev)
                low_conf = 'BROWSER_PROBLEM_CHECK_FALLBACK' if actual_source == 'browser' else None
                problem_key = extract_usage_key(ev, prefer_problem=True) or unit_key
                earned, possible = _submission_score(ev)
                feat.submissions.append({
                    'submitted_at': ev.event_time, 'problem_usage_key': problem_key,
                    'event_type': et, 'event_source': actual_source,
                    'low_confidence': low_conf, 'earned': earned, 'possible': possible,
                    'attempt_index': (ev.raw_event or {}).get('attempts'),
                    'payload': ev.raw_event or {}, 'context': ev.raw_context or {},
                    'event_id': ev.raw_event_id,
                })
                if low_conf and not feat.low_confidence_reason:
                    feat.low_confidence_reason = low_conf
                continue
            if et in SHOWANSWER_EVENTS:
                feat.showanswer_count += 1
                feat.answer_reveal_requests.append({
                    'problem_usage_key': extract_usage_key(ev, prefer_problem=True),
                    'requested_at': ev.event_time.isoformat(),
                })
                continue
        if current:
            _finalize_attempt(current, reset_times)
            features.append(current)
    return features
