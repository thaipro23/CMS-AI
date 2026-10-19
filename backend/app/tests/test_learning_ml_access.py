from datetime import datetime, timedelta
from importlib import import_module, util
from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.services.learning_analytics.ml_anomaly import MODEL_VERSION
from app.services.learning_analytics.ml_features import FEATURE_VERSION, fingerprint

NOW = datetime(2026, 10, 16, 8)

@pytest.fixture
def data(monkeypatch):
    monkeypatch.setattr(settings, 'analytics_ml_mode', 'shadow')
    monkeypatch.setattr(settings, 'analytics_ml_pilot_class_ids', 'class')
    monkeypatch.setattr(settings, 'analytics_ml_min_reference_students', 30)
    return {'ml': {'family': 'video', 'class_id': 'class', 'course_id': 'course',
        'unit_usage_key': None, 'status': 'SCORED', 'model_version': MODEL_VERSION,
        'feature_version': FEATURE_VERSION, 'runtime_version': '1.6.1',
        'baseline_score':12.,'primary_method':'median_mad','comparison_status':'AGREES',
        'comparison_percentile':94.,'reference_scope':fingerprint(['course']),
        'measurement':{'observed_playback_rate':2.,'measured_videos':3,'pooled_course_count':1},
        'cutoff': NOW.isoformat(), 'calculated_at': NOW.isoformat(), 'snapshot_calculated_at': NOW.isoformat(),
        'reference_count': 55, 'anomaly_score': .65, 'reference_percentile': 95, 'outlier': True,
        'features': {'watch_ratio': .2, 'reference_username': 'private'},
        'reference_usernames': ['private'], 'answer_json': {'secret': 1}, 'reason_codes': [],
        'deviations': [{'feature': 'watch_ratio', 'value': .2, 'reference_median': .8, 'difference': -.6,
            'reference_mad':.1,'robust_deviation':6.,'other_username': 'private'}]}}

def serialize(data, **kwargs):
    path = 'app.services.learning_analytics.ml_presentation'
    assert util.find_spec(path), 'Missing scoped ML presentation'
    return import_module(path).serialize_ml_analysis(data, class_id='class', course_id='course',
        family='video', snapshot_calculated_at=NOW, now=NOW, **kwargs)

def test_only_allowlisted_measured_evidence_is_visible(data):
    result = serialize(data)
    assert result['status'] == 'SCORED' and result['reference_count'] == 55
    assert result['features'] == {'watch_ratio': .2}
    assert 'private' not in str(result) and 'answer_json' not in result
    assert set(result['deviations'][0]) == {'feature', 'value', 'reference_median', 'difference','reference_mad','robust_deviation'}
    assert 'outlier' not in result and 'anomaly_score' not in result

@pytest.mark.parametrize(('key', 'value'), [('class_id','other'),('course_id','other'),
    ('family','quiz'),('unit_usage_key','other'),('feature_version','old'),('model_version','old'),
    ('runtime_version','0'),('cutoff',(NOW+timedelta(seconds=1)).isoformat()),
    ('snapshot_calculated_at',(NOW-timedelta(seconds=1)).isoformat()),
    ('calculated_at',None),('reference_count',29),('reference_count',True),
    ('baseline_score',float('nan')),('reference_percentile',101),('primary_method','unknown'),
    ('features',[]),('deviations',None),('reason_codes',None)])
def test_mismatched_or_malformed_evidence_cannot_show_active_outlier(data,key,value):
    data['ml'][key]=value
    result=serialize(data)
    assert result['status']=='STALE' and result.get('outlier') is None
    assert result['reference_percentile'] is None

def test_off_and_outside_pilot_hide_old_outliers(data,monkeypatch):
    monkeypatch.setattr(settings,'analytics_ml_mode','off')
    assert serialize(data)['status']=='DISABLED'
    monkeypatch.setattr(settings,'analytics_ml_mode','shadow')
    monkeypatch.setattr(settings,'analytics_ml_pilot_class_ids','other')
    assert serialize(data).get('outlier') is None

def test_legacy_evidence_waits_for_recalculation(data):
    assert serialize({})['status']=='NOT_READY'

def test_old_cutoff_cannot_show_active_outlier(data):
    data['ml']['cutoff']=(NOW-timedelta(days=8)).isoformat()
    assert serialize(data)['status']=='STALE'

def test_unscored_evidence_does_not_expose_scores(data):
    data['ml'].update(status='INSUFFICIENT_DATA',reference_count=20)
    assert serialize(data).get('outlier') is None
    assert serialize(data)['reference_percentile'] is None

def test_quiz_outsider_is_rejected_before_any_database_read():
    from app.services.learning_analytics.quiz_detail import read_quiz_detail
    parent=SimpleNamespace(db=None,_class_student_usernames=lambda _: {'allowed'})
    assert read_quiz_detail(parent,class_id='class',course_id='course',username='other')['status']=='OUTSIDE_CLASS'


def test_free_text_in_reason_codes_is_not_exposed(data):
    data['ml']['reason_codes']=['BASELINE_TOO_SMALL','reference-user-private']
    assert serialize(data)['reason_codes']==['BASELINE_TOO_SMALL']


def test_low_reference_confidence_and_explanatory_fields_are_exposed(data):
    data['ml']['reference_count']=35
    result=serialize(data)
    assert result['status']=='SCORED' and result['confidence']=='LOW'
    assert result['primary_method']=='median_mad' and result['comparison_status']=='AGREES'
    assert result['measurement']['observed_playback_rate']==2.


def test_changed_pool_configuration_invalidates_saved_ranking(data,monkeypatch):
    monkeypatch.setitem(settings.__dict__,'analytics_ml_video_reference_course_ids','other-course')
    assert serialize(data)['status']=='STALE'
