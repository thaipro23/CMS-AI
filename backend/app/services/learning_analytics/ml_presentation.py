"""Read-only ML presentation. Never expose reference identities or fit on GET."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.core.config import settings
from .ml_anomaly import MODEL_VERSION
from .ml_features import FEATURE_VERSION, utc
from .ml_workflow import ml_enabled

FEATURES = {'video': {'completion_watch_gap', 'watch_ratio', 'seeks_per_watch_minute', 'passive_ratio'},
    'quiz': {'seconds_per_independent_submission', 'successful_resets_per_attempt', 'submissions_per_response'}}


REASONS = {
    'BASELINE_TOO_SMALL', 'CANCELLED', 'CONSTANT_FEATURES', 'FEATURE_SCHEMA_MISMATCH',
    'INVALID_MEASUREMENT', 'MODEL_UNAVAILABLE', 'DUPLICATE_OR_MISSING_VIDEO_IDENTITY',
    'INSUFFICIENT_INDEPENDENT_TIMING', 'INSUFFICIENT_MEASURABLE_VIDEOS',
    'INSUFFICIENT_MEASURABLE_WATCH', 'INVALID_MEASUREMENT_TIME', 'MISSING_CONTENT_VERSION',
    'MISSING_QUESTION_IDENTITY', 'MISSING_SESSION_MAPPING', 'MISSING_VIDEO_DURATION',
    'SOURCE_TOO_LARGE', 'UNTRUSTED_QUIZ_SESSION', 'ML_SOURCE_TOO_LARGE',
    'ML_WORKFLOW_FAILED', 'NO_MEASURED_ACTIVITY', 'UNTRUSTED_SUBMISSION_TIMING', 'UNTRUSTED_RESET_ASSOCIATION',
}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def serialize_ml_analysis(evidence: dict, *, class_id: str | None, course_id: str | None,
                          family: str, snapshot_calculated_at: datetime | None,
                          unit_usage_key: str | None = None, now: datetime | None = None) -> dict:
    empty = {'family': family, 'status': 'DISABLED', 'reason_codes': [],
        'reference_count': 0, 'outlier': None, 'anomaly_score': None,
        'reference_percentile': None, 'features': {}, 'deviations': [], 'calculated_at': None}
    if not ml_enabled(class_id):
        return empty
    data = evidence.get('ml') if isinstance(evidence, dict) else None
    if not isinstance(data, dict):
        return {**empty, 'status': 'NOT_READY', 'reason_codes': ['RECALCULATION_REQUIRED']}
    cutoff, stamp, now = utc(data.get('cutoff')), utc(snapshot_calculated_at), utc(now or datetime.utcnow())
    stale = (data.get('class_id') != class_id or data.get('course_id') != course_id
        or data.get('unit_usage_key') != unit_usage_key or data.get('family') != family
        or data.get('model_version') != MODEL_VERSION or data.get('feature_version') != FEATURE_VERSION
        or cutoff is None or stamp is None or now is None or cutoff > now or cutoff < stamp
        or utc(data.get('snapshot_calculated_at')) != stamp or utc(data.get('calculated_at')) != cutoff
        or (cutoff is not None and now is not None and cutoff < now-timedelta(hours=settings.analytics_snapshot_stale_hours)))
    if (not isinstance(data.get('features'), dict) or not isinstance(data.get('deviations'), list)
            or not isinstance(data.get('reason_codes'), list)):
        stale = True
    count, status = data.get('reference_count'), data.get('status')
    if type(count) is not int or not 0 <= count <= 5000:
        stale = True
    if status == 'SCORED':
        percentile, score = data.get('reference_percentile'), data.get('anomaly_score')
        if (data.get('runtime_version') != '1.6.1' or type(data.get('outlier')) is not bool
                or not _finite(percentile) or not 0 <= percentile <= 100
                or not _finite(score) or score < 0 or type(count) is not int
                or count < settings.analytics_ml_min_reference_students):
            stale = True
    if stale or status not in {'SCORED', 'INSUFFICIENT_DATA', 'ERROR'}:
        return {**empty, 'status': 'STALE', 'reason_codes': ['RECALCULATION_REQUIRED']}
    allowed = FEATURES.get(family, set())
    features = {k: float(v) for k, v in data['features'].items() if k in allowed and _finite(v)}
    deviations = [{k: d[k] for k in ('feature', 'value', 'reference_median', 'difference')}
        for d in data['deviations'] if isinstance(d, dict) and d.get('feature') in allowed
        and all(_finite(d.get(k)) for k in ('value', 'reference_median', 'difference'))][:3]
    return {**empty, 'status': status, 'reference_count': count, 'features': features,
        'deviations': deviations, 'calculated_at': cutoff.isoformat(),
        'reason_codes': [s for s in data['reason_codes'] if isinstance(s, str) and s in REASONS][:10],
        'outlier': data.get('outlier') if status == 'SCORED' else None,
        'anomaly_score': data.get('anomaly_score') if status == 'SCORED' else None,
        'reference_percentile': data.get('reference_percentile') if status == 'SCORED' else None}
