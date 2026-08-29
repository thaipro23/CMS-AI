from __future__ import annotations

import re
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
    low_confidence_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

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


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == '':
            return None
        return float(value)
    except Exception:
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
    keys = (
        ('problem_id', 'problem_usage_key', 'usage_key', 'item_usage_key', 'module_id', 'block_id')
        if prefer_problem else
        ('unit_usage_key', 'unit_key', 'usage_key', 'module_id', 'block_id', 'problem_id', 'problem_usage_key')
    )
    for key in keys:
        value = _safe_str(payload.get(key)) or _safe_str(context.get(key))
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
        value = _safe_str(payload.get(key)) or _safe_str(context.get(key))
        if value:
            return value
    return None


def extract_unit_reset_nonce(event: EventLike) -> str | None:
    payload = event.raw_event or {}
    for key in ('unit_reset_nonce', 'nonce', 'reset_nonce'):
        value = _safe_str(payload.get(key))
        if value:
            return value
    if event.page_url:
        match = re.search(r'unit_reset_nonce=([^&#]+)', event.page_url)
        if match:
            return match.group(1)
    return None


def _submission_score(event: EventLike) -> tuple[float | None, float | None]:
    payload = event.raw_event or {}
    earned = _safe_float(payload.get('grade')) or _safe_float(payload.get('score')) or _safe_float(payload.get('earned'))
    possible = _safe_float(payload.get('max_grade')) or _safe_float(payload.get('max_score')) or _safe_float(payload.get('possible'))
    return earned, possible


def _finalize_attempt(feature: QuizAttemptFeature, reset_times: list[datetime]) -> None:
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
    previous = feature.started_at
    for item in ordered_submits:
        current = item.get('submitted_at')
        if previous and current and current >= previous:
            deltas.append((current - previous).total_seconds())
        if current:
            previous = current
    if deltas:
        feature.median_time_per_question_seconds = round(float(median(deltas)), 2)
        mean = sum(deltas) / len(deltas)
        if mean > 0:
            variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
            cv = (variance ** 0.5) / mean
        else:
            cv = 0.0
        feature.suspicious_quiz_speed = len(deltas) >= 3 and feature.median_time_per_question_seconds <= 5.0 and cv <= 0.35
    if len(reset_times) >= 2:
        reset_deltas = [(b - a).total_seconds() for a, b in zip(reset_times, reset_times[1:]) if b >= a]
        if reset_deltas and median(reset_deltas) <= 120 and feature.submissions:
            feature.fishing_pattern = True
    if not feature.started_at and feature.submissions:
        feature.low_confidence_reason = 'MISSING_QUIZ_SESSION_START'
    feature.evidence = {
        'assigned_problem_count': len(feature.assigned_problem_usage_keys),
        'distinct_assigned_problem_count': len(unique),
        'submission_count': len(feature.submissions),
        'showanswer_count': feature.showanswer_count,
        'repeat_rate': feature.repeat_rate,
        'median_time_per_question_seconds': feature.median_time_per_question_seconds,
        'server_canonical_submission': True,
        'showanswer_policy': 'neutral_unless_same_item_repeated_in_same_attempt',
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
                )
                continue
            if et == QUIZ_SESSION_STATUS:
                # Status refreshes an open attempt only. It never creates one by itself.
                continue
            if et == QUIZ_SESSION_RESET:
                if ev.event_time:
                    reset_times.append(ev.event_time)
                if current:
                    current.reset_count += 1
                    _finalize_attempt(current, reset_times)
                    features.append(current)
                    current = None
                continue
            feat = ensure_attempt(ev)
            if et in ITEMBANK_EVENTS:
                key = extract_usage_key(ev, prefer_problem=True)
                if key and key not in {'UNKNOWN_QUIZ_UNIT', unit_key}:
                    feat.assigned_problem_usage_keys.append(key)
                payload = ev.raw_event or {}
                for candidate in ('location', 'itembank_location', 'library_key', 'block_id'):
                    val = _safe_str(payload.get(candidate))
                    if val:
                        feat.itembank_locations.append(val)
                continue
            if et in SUBMIT_EVENTS:
                # Server events are canonical. Browser problem_check is fallback only.
                if et == 'problem_check' and str(ev.event_source or '').lower() not in {'server', 'openedx_tracking_log'}:
                    # Keep it only when no submitted event exists later; tag evidence.
                    low_conf = 'BROWSER_PROBLEM_CHECK_FALLBACK'
                else:
                    low_conf = None
                problem_key = extract_usage_key(ev, prefer_problem=True) or unit_key
                earned, possible = _submission_score(ev)
                feat.submissions.append({'submitted_at': ev.event_time, 'problem_usage_key': problem_key, 'event_type': et, 'event_source': ev.event_source, 'low_confidence': low_conf})
                if earned is not None:
                    feat.score_earned = (feat.score_earned or 0) + earned
                if possible is not None:
                    feat.score_possible = (feat.score_possible or 0) + possible
                if low_conf and not feat.low_confidence_reason:
                    feat.low_confidence_reason = low_conf
                continue
            if et in SHOWANSWER_EVENTS:
                feat.showanswer_count += 1
                continue
        if current:
            _finalize_attempt(current, reset_times)
            features.append(current)
    return features
