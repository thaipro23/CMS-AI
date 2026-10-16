"""Deterministic cohort outlier scoring, independent of rules and grades."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Callable

from .ml_features import FEATURE_VERSION, MLFeatureRow, fingerprint, unique_reference_rows

MODEL_VERSION = 'isolation_forest_shadow_v1'


def result_key(row: MLFeatureRow) -> str:
    return fingerprint([row.family, row.cohort_key, row.subject_key])


def base_result(row: MLFeatureRow | None, *, family: str = '', reasons: list[str] | None = None,
                reference_count: int = 0) -> dict:
    return {'family': row.family if row else family, 'status': 'INSUFFICIENT_DATA',
        'algorithm': 'IsolationForest', 'model_version': MODEL_VERSION,
        'feature_version': FEATURE_VERSION, 'reason_codes': reasons or [],
        'reference_count': reference_count, 'cohort_digest': None,
        'cutoff': row.cutoff.isoformat() if row else None,
        'features': dict(row.features) if row else {}, 'anomaly_score': None,
        'reference_percentile': None, 'outlier': None, 'deviations': []}


def _valid(row: MLFeatureRow) -> bool:
    return bool(row.features) and all(isinstance(v, (int, float)) and math.isfinite(v)
                                      for v in row.features.values())


def score_cohorts(rows: list[MLFeatureRow], *, min_students: int = 50,
                  max_students: int = 5000, cancelled: Callable[[], bool] | None = None) -> dict[str, dict]:
    min_students = max(50, int(min_students))
    max_students = max(min_students, min(5000, int(max_students)))
    if min_students > 5000:
        min_students = 5000
        max_students = 5000
    groups, results = defaultdict(list), {}
    for row in unique_reference_rows(rows):
        if not _valid(row):
            invalid = base_result(None, family=row.family, reasons=['INVALID_MEASUREMENT'])
            invalid['cutoff'] = row.cutoff.isoformat()
            results[result_key(row)] = invalid
        else:
            groups[(row.family, row.cohort_key)].append(row)
    for group in groups.values():
        schema = Counter(tuple(sorted(r.features)) for r in group).most_common(1)[0][0]
        eligible = []
        for r in group:
            if tuple(sorted(r.features)) != schema:
                results[result_key(r)] = base_result(r, reasons=['FEATURE_SCHEMA_MISMATCH'])
            else:
                eligible.append(r)
        # Stable hash sampling avoids bias from DB order or username order.
        ordered = sorted(eligible, key=lambda r: fingerprint([r.cohort_key, r.subject_key]))
        reference = ordered[:max_students]
        count = len(reference)
        if count < min_students:
            for r in eligible:
                results[result_key(r)] = base_result(r, reasons=['BASELINE_TOO_SMALL'], reference_count=count)
            continue
        if cancelled and cancelled():
            for r in eligible:
                result = base_result(r, reasons=['CANCELLED'], reference_count=count)
                result['status'] = 'ERROR'
                results[result_key(r)] = result
            continue
        try:
            import numpy as np
            import sklearn
            from sklearn.ensemble import IsolationForest
            from threadpoolctl import threadpool_limits

            matrix = np.asarray([[r.features[k] for k in schema] for r in reference], dtype=float)
            if not np.any(np.ptp(matrix, axis=0) > 0):
                for r in eligible:
                    results[result_key(r)] = base_result(r, reasons=['CONSTANT_FEATURES'], reference_count=count)
                continue
            model = IsolationForest(n_estimators=100, max_samples=min(256, count),
                contamination='auto', random_state=42, n_jobs=1)
            digest = fingerprint([[r.subject_key, r.features, r.cutoff.isoformat()] for r in reference])
            with threadpool_limits(limits=1):
                model.fit(matrix)
                reference_scores = np.sort(-model.score_samples(matrix))
                med = np.median(matrix, axis=0)
                iqr = np.percentile(matrix, 75, axis=0) - np.percentile(matrix, 25, axis=0)
                for offset in range(0, len(eligible), 512):
                    chunk = eligible[offset:offset+512]
                    samples = np.asarray([[r.features[k] for k in schema] for r in chunk], dtype=float)
                    scores = -model.score_samples(samples)
                    for r, sample, score in zip(chunk, samples, scores):
                        # These describe observed deviations, not model attribution.
                        deltas = [(i, float(sample[i] - med[i]),
                                   float(abs(sample[i] - med[i]) / max(float(iqr[i]), 1e-9)))
                                  for i in range(len(schema))]
                        deviations = [{'feature': schema[i], 'value': float(sample[i]),
                            'reference_median': float(med[i]), 'difference': delta}
                            for i, delta, _ in sorted(deltas, key=lambda x: -x[2])[:3]]
                        below = np.searchsorted(reference_scores, score, side='left')
                        equal = np.searchsorted(reference_scores, score, side='right') - below
                        result = base_result(r, reference_count=count)
                        result.update(status='SCORED', cohort_digest=digest,
                            runtime_version=sklearn.__version__, anomaly_score=round(float(score), 8),
                            reference_percentile=round(float((below + equal / 2) / count * 100), 2),
                            outlier=bool(-score - model.offset_ < 0), deviations=deviations)
                        results[result_key(r)] = result
        except Exception:
            # The workflow logs counts. Never put exception text, answers or identities in evidence.
            for r in eligible:
                result = base_result(r, reasons=['MODEL_UNAVAILABLE'], reference_count=count)
                result['status'] = 'ERROR'
                results[result_key(r)] = result
    return results
