from datetime import datetime
from importlib import import_module, util

import pytest

from app.services.learning_analytics.ml_features import MLFeatureRow


def scorer():
    name = 'app.services.learning_analytics.ml_anomaly'
    assert util.find_spec(name), 'ML cohort scorer is not implemented'
    return import_module(name)


def rows(n=50):
    return [MLFeatureRow(f'u{i}', 'video', 'cohort',
        {'completion_watch_gap': i/1000, 'watch_ratio': .7+i/5000,
         'seeks_per_watch_minute': 1+i/100, 'passive_ratio': .2+i/1000},
         datetime(2026, 10, 9)) for i in range(n)]


def test_baseline_counts_students_not_events():
    result = scorer().score_cohorts(rows(49)*3)
    assert len(result) == 49
    assert all(r['status'] == 'INSUFFICIENT_DATA' and r['reference_count'] == 49 for r in result.values())


def test_fifty_distinct_students_can_be_scored():
    result = scorer().score_cohorts(rows())
    assert len(result) == 50
    assert all(r['status'] == 'SCORED' for r in result.values())
    assert not any('probability' in r or 'username' in r for r in result.values())


def test_row_order_cannot_change_scores_or_digest():
    a = scorer().score_cohorts(rows())
    assert scorer().score_cohorts(list(reversed(rows()))) == a


def test_constant_features_do_not_force_outliers():
    constant = [MLFeatureRow(f'u{i}', 'video', 'c', {'x': 1.}, datetime(2026, 10, 9)) for i in range(50)]
    result = scorer().score_cohorts(constant)
    assert all(r['reason_codes'] == ['CONSTANT_FEATURES'] for r in result.values())


def test_sample_cap_and_out_of_sample_target_are_deterministic():
    result = scorer().score_cohorts(rows(80), max_students=50)
    assert len(result) == 80
    assert all(r['reference_count'] == 50 for r in result.values())
    assert scorer().score_cohorts(rows(80)[::-1], max_students=50) == result


def test_conspicuous_synthetic_outlier_ranks_above_group_median():
    from statistics import median
    data = rows(80)
    data.append(MLFeatureRow('extreme', 'video', 'cohort',
        {'completion_watch_gap': .9, 'watch_ratio': .01,
         'seeks_per_watch_minute': 100., 'passive_ratio': .99}, datetime(2026, 10, 9)))
    result = scorer().score_cohorts(data)
    extreme = result[scorer().result_key(data[-1])]
    assert extreme['anomaly_score'] > median(r['anomaly_score'] for r in result.values())
    assert extreme['outlier'] is True
    assert len(extreme['deviations']) <= 3


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_invalid_features_are_excluded_without_crashing_group(bad):
    data = rows()
    data.append(MLFeatureRow('bad', 'video', 'cohort', {'bad': bad}, datetime(2026, 10, 9)))
    result = scorer().score_cohorts(data)
    assert result[scorer().result_key(data[-1])]['status'] == 'INSUFFICIENT_DATA'


def test_family_and_cohort_keys_cannot_overwrite_same_student():
    data = rows()
    data += [MLFeatureRow(r.subject_key, 'quiz', 'other', r.features, r.cutoff) for r in rows()]
    assert len(scorer().score_cohorts(data)) == 100
