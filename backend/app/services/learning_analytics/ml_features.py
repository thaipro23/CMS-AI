"""Measured, content-scoped features. Missing telemetry never becomes zero."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any

from .quiz_attempt_analyzer import SERVER_SESSION_PROVENANCE, SERVER_SUBMISSION_PROVENANCE, SERVER_RESET_PROVENANCE
from .quiz_integrity_rules import _burst_times

FEATURE_VERSION = 'learning_ml_features_v1'


@dataclass(frozen=True)
class MLFeatureRow:
    subject_key: str
    family: str
    cohort_key: str
    features: dict[str, float]
    cutoff: datetime


@dataclass(frozen=True)
class MLFeatureBuild:
    row: MLFeatureRow | None
    reasons: tuple[str, ...] = ()


def value(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def utc(value_: Any) -> datetime | None:
    try:
        dt = value_ if isinstance(value_, datetime) else datetime.fromisoformat(str(value_))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except (ValueError, TypeError):
        return None


def fingerprint(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), default=str).encode()).hexdigest()


def video_identity(key: Any) -> str:
    key = str(key or '').strip()
    return key.rsplit('+block@', 1)[-1] if key.startswith('block-v1:') else key


def video_outline(sessions: list[Any]) -> tuple[str, set[str]]:
    outline = fingerprint(sorted([(value(s, 'session_key'), value(s, 'components_json'))
        for s in sessions], key=lambda x: str(x[0]))) if sessions else ''
    keys = {video_identity(item.get('usage_key')) for s in sessions
        for item in (value(s, 'components_json') or {}).get('components', [])
        if item.get('block_type') == 'video' and item.get('usage_key')}
    return outline, keys


def number(v: Any) -> float | None:
    try:
        result = float(v)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def unique_reference_rows(rows: list[MLFeatureRow]) -> list[MLFeatureRow]:
    # Deterministic even for malformed duplicate inputs, never count enrollments.
    unique = {}
    for row in sorted(rows, key=lambda r: (r.family, r.cohort_key, r.subject_key,
                                         fingerprint(r.features))):
        unique.setdefault((row.family, row.cohort_key, row.subject_key), row)
    return list(unique.values())


def build_video_features(*, subject_key: str, course_id: str, outline_fingerprint: str,
                         videos: list[Any], cutoff: datetime) -> MLFeatureBuild:
    cutoff = utc(cutoff)
    if cutoff is None or not outline_fingerprint:
        return MLFeatureBuild(None, ('MISSING_SESSION_MAPPING',))
    measured, reasons, seen = [], set(), set()
    for v in videos:
        identity = video_identity(value(v, 'video_id'))
        if not identity or identity in seen:
            reasons.add('DUPLICATE_OR_MISSING_VIDEO_IDENTITY')
            continue
        seen.add(identity)
        duration = number(value(v, 'duration_seconds'))
        if not duration:
            reasons.add('MISSING_VIDEO_DURATION')
            continue
        if value(v, 'session_index') is None:
            reasons.add('MISSING_SESSION_MAPPING')
            continue
        when = utc(value(v, 'last_event_at'))
        if when is None or when > cutoff:
            reasons.add('INVALID_MEASUREMENT_TIME')
            continue
        fields = [number(value(v, k)) for k in ('completion_percent',
            'estimated_watch_seconds', 'passive_watch_seconds', 'seek_count')]
        if any(x is None for x in fields):
            reasons.add('INVALID_MEASUREMENT')
            continue
        completion, watch, passive, seeks = fields
        measured.append((duration, min(1., completion / 100), min(watch, duration),
                         min(passive, watch), seeks))
    if len(measured) < 3:
        return MLFeatureBuild(None, tuple(sorted(reasons | {'INSUFFICIENT_MEASURABLE_VIDEOS'})))
    duration = sum(x[0] for x in measured)
    watch = sum(x[2] for x in measured)
    if watch <= 0:
        return MLFeatureBuild(None, ('INSUFFICIENT_MEASURABLE_WATCH',))
    completion = sum(x[0] * x[1] for x in measured) / duration
    watch_ratio = watch / duration
    features = {'completion_watch_gap': completion - watch_ratio, 'watch_ratio': watch_ratio,
        'seeks_per_watch_minute': sum(x[4] for x in measured) / (watch / 60),
        'passive_ratio': min(1., sum(x[3] for x in measured) / watch)}
    exposure = '3-5' if len(measured) <= 5 else '6-10' if len(measured) <= 10 else '11+'
    cohort = fingerprint([FEATURE_VERSION, 'video', course_id, outline_fingerprint, exposure])
    return MLFeatureBuild(MLFeatureRow(subject_key, 'video', cohort, features, cutoff), tuple(sorted(reasons)))


def build_quiz_features(*, subject_key: str, course_id: str, unit_usage_key: str,
                        attempt: Any, items: list[Any], cutoff: datetime) -> MLFeatureBuild:
    cutoff = utc(cutoff)
    evidence = value(attempt, 'evidence_json', {}) or {}
    started = utc(value(attempt, 'started_at'))
    ended = utc(value(attempt, 'ended_at'))
    nonce = str(value(attempt, 'unit_reset_nonce') or '')
    if (cutoff is None or started is None or ended is None or started > ended or ended > cutoff
            or not re.fullmatch(r'quiz-session:[^\s:]+', nonce)
            or evidence.get('session_event_provenance') != SERVER_SESSION_PROVENANCE
            or not evidence.get('start_observed')):
        return MLFeatureBuild(None, ('UNTRUSTED_QUIZ_SESSION',))
    if len(items) > 2000:
        return MLFeatureBuild(None, ('SOURCE_TOO_LARGE',))
    selected = [i for i in items if (t := utc(value(i, 'submitted_at'))) is not None
                and started <= t <= ended
                and value(i, 'unit_reset_nonce') in (None, '', nonce)]
    if not selected:
        return MLFeatureBuild(None, ('MISSING_QUESTION_IDENTITY',))
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', str(value(i, 'content_version') or '')) for i in selected):
        return MLFeatureBuild(None, ('MISSING_CONTENT_VERSION',))
    empty_hash = hashlib.sha256(b'').hexdigest()
    if any(not re.fullmatch(r'[0-9a-f]{64}', str(value(i, 'question_hash') or ''))
           or value(i, 'question_hash') == empty_hash or not value(i, 'input_slot') for i in selected):
        return MLFeatureBuild(None, ('MISSING_QUESTION_IDENTITY',))
    identities = sorted({(value(i, 'content_version'), value(i, 'question_hash'),
                          value(i, 'input_slot'), str(value(i, 'variant') or '')) for i in selected})
    if evidence.get('submission_timing_provenance') != SERVER_SUBMISSION_PROVENANCE:
        return MLFeatureBuild(None, ('UNTRUSTED_SUBMISSION_TIMING',))
    if evidence.get('reset_event_provenance') != SERVER_RESET_PROVENANCE:
        return MLFeatureBuild(None, ('UNTRUSTED_RESET_ASSOCIATION',))
    # Use only persisted server timing, not the browser/item timestamp as proof.
    problems = {value(i, 'problem_usage_key') for i in selected}
    timings = [{'problem_usage_key': p, 'submitted_at': t} for s in evidence.get('server_submission_times', [])
               if (p := value(s, 'problem_usage_key')) in problems
               and (t := utc(value(s, 'submitted_at'))) is not None and started <= t <= ended]
    if len(timings) > 2000:
        return MLFeatureBuild(None, ('SOURCE_TOO_LARGE',))
    burst = _burst_times(timings)
    points = sorted({x['submitted_at'] for x in timings if x['submitted_at'] not in burst
                     and x['submitted_at'] > started})
    if len(points) < 6:
        return MLFeatureBuild(None, ('INSUFFICIENT_INDEPENDENT_TIMING',))
    # First response is measured from the actual persisted start.
    gaps = [(b-a).total_seconds() for a, b in zip([started, *points[:-1]], points)]
    resets = {t for raw in evidence.get('successful_reset_times', [])
              if (t := utc(raw)) is not None and started <= t <= ended}
    features = {'seconds_per_independent_submission': float(median(gaps)),
        'successful_resets_per_attempt': float(len(resets)),
        'submissions_per_response': len(selected) / len(identities)}
    cohort = fingerprint([FEATURE_VERSION, 'quiz', course_id, unit_usage_key, identities])
    return MLFeatureBuild(MLFeatureRow(subject_key, 'quiz', cohort, features, cutoff))
