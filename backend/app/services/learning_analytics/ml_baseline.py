"""Explainable directed median/MAD ranking and optional forest comparison."""
from __future__ import annotations


def percentiles(scores, reference):
    import numpy as np
    ordered = np.sort(reference)
    left = np.searchsorted(ordered, scores, side='left')
    right = np.searchsorted(ordered, scores, side='right')
    return (left+right)/2/len(ordered)*100


def video_scores(reference, samples, schema, *, seed=42):
    import numpy as np
    med = np.median(reference, axis=0)
    mad = np.median(np.abs(reference-med), axis=0)
    floor = np.asarray([1. if k == 'seeks_per_watch_minute' else .05 for k in schema])
    scale = np.maximum(1.4826*mad, floor)

    def contributions(matrix):
        values = (matrix-med)/scale
        for i, key in enumerate(schema):
            values[:, i] = (-values[:, i] if key == 'watch_ratio' else values[:, i]
                if key == 'completion_watch_gap' else np.abs(values[:, i]))
        return np.maximum(values, 0.)

    reference_baseline = np.max(contributions(reference), axis=1)
    deviations = contributions(samples)
    baseline = np.max(deviations, axis=1)
    result = {'baseline': baseline, 'percentiles': percentiles(baseline, reference_baseline),
        'medians': med, 'mads': mad, 'contributions': deviations, 'comparison_status': 'UNAVAILABLE',
        'comparison': None, 'comparison_percentiles': None, 'rank_correlation': None,
        'top_five_overlap': None, 'runtime_version': None}
    try:
        import sklearn
        from sklearn.ensemble import IsolationForest
        from threadpoolctl import threadpool_limits
        model = IsolationForest(n_estimators=200, max_samples=min(256, len(reference)),
            contamination='auto', random_state=seed, n_jobs=1)
        with threadpool_limits(limits=1):
            model.fit(reference)
            ref_if = -model.score_samples(reference)
            scores = np.concatenate([-model.score_samples(samples[i:i+512]) for i in range(0, len(samples), 512)])
        a, b = percentiles(reference_baseline, reference_baseline), percentiles(ref_if, ref_if)
        informative = bool(np.ptp(a) and np.ptp(b))
        correlation = float(np.corrcoef(a,b)[0,1]) if informative else None
        k = min(5, len(reference))
        first = set(np.flatnonzero(reference_baseline >= np.sort(reference_baseline)[-k]))
        second = set(np.flatnonzero(ref_if >= np.sort(ref_if)[-k]))
        overlap = len(first & second)/max(len(first), len(second))
        result.update(comparison=scores, comparison_percentiles=percentiles(scores, ref_if),
            comparison_status=('AGREES' if correlation >= .8 and overlap >= .8 else 'DIFFERS')
                if informative else 'UNINFORMATIVE',
            rank_correlation=correlation, top_five_overlap=overlap, runtime_version=sklearn.__version__)
    except Exception:
        # A valid statistical baseline survives failure of the optional comparison.
        pass
    return result
