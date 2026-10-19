"""Behavioral acceptance tests for video-only relative ranking v2."""
from datetime import datetime, timedelta
from importlib import import_module
from itertools import combinations
import random

import pytest

from app.services.learning_analytics.ml_anomaly import result_key, score_cohorts
from app.services.learning_analytics.ml_features import MLFeatureRow, build_video_features
from app.services.learning_analytics.video_watch_calculator import VideoEventInput

NOW = datetime(2026, 10, 19, 4)


def measured(coverage=80., rate=1., index=0):
    return dict(video_id=f'v{index}', duration_seconds=100., session_index=1,
        completion_percent=100., estimated_watch_seconds=coverage/rate,
        passive_watch_seconds=0., seek_count=0, last_event_at=NOW,
        evidence_json={'playback_measurement': {'version': 'video_playback_v1',
            'complete_history': True, 'observed_intervals': 1, 'unknown_intervals': 0,
            'media_seconds': coverage, 'wall_seconds': coverage/rate,
            'passive_media_seconds': 0.}})


def features(videos):
    return build_video_features(subject_key='u', course_id='course',
        outline_fingerprint='outline', videos=videos, cutoff=NOW)


def cohort(n=50):
    rng = random.Random(31019)
    return [MLFeatureRow(str(i), 'video', 'same', {
        'completion_watch_gap': rng.uniform(.01,.15), 'watch_ratio': rng.uniform(.72,.97),
        'seeks_per_watch_minute': rng.uniform(.1,1.8), 'passive_ratio': rng.uniform(.05,.3)}, NOW)
        for i in range(n)]


def test_thirty_distinct_people_score_with_low_confidence():
    scores=score_cohorts(cohort(30)*2)
    assert len(scores)==30
    assert all(s['status']=='SCORED' and s['reference_count']==30 and s['confidence']=='LOW' for s in scores.values())


def test_twenty_nine_people_are_not_enough():
    assert all(s['reason_codes']==['BASELINE_TOO_SMALL'] for s in score_cohorts(cohort(29)).values())


def test_fifty_people_have_standard_confidence_and_mad_baseline():
    scores=score_cohorts(cohort())
    assert all(s['confidence']=='STANDARD' and s['primary_method']=='median_mad' for s in scores.values())
    assert all(s['baseline_score'] is not None and s['comparison_percentile'] is not None for s in scores.values())
    assert all(s.get('outlier') is None for s in scores.values())


def test_fast_and_normal_viewers_with_same_content_have_identical_features():
    one=features([measured(90,1,j) for j in range(3)])
    two=features([measured(90,2,j) for j in range(3)])
    assert one.row.features==two.row.features
    assert one.row.features['watch_ratio']==pytest.approx(.9)
    assert two.row.metadata['observed_playback_rate']==pytest.approx(2.)


def test_missing_playback_history_is_not_assumed_to_be_one_x():
    videos=[measured(index=j) for j in range(3)]
    videos[0]['evidence_json']={}
    result=features(videos)
    assert result.row is None and 'MISSING_PLAYBACK_MEASUREMENT' in result.reasons


@pytest.mark.parametrize('key,bad', [('complete_history',False),('unknown_intervals',1),
    ('media_seconds',None),('wall_seconds',float('nan'))])
def test_incomplete_or_invalid_playback_is_excluded(key,bad):
    videos=[measured(index=j) for j in range(3)]
    videos[0]['evidence_json']['playback_measurement'][key]=bad
    assert features(videos).row is None


def test_actual_measured_zero_coverage_does_not_become_missing():
    videos=[measured(0.,index=j) for j in range(3)]
    for v in videos:v['evidence_json']['playback_measurement']['wall_seconds']=1.
    result=features(videos)
    assert result.row is not None and result.row.features['watch_ratio']==0.


def playback(events, **kwargs):
    module=import_module('app.services.learning_analytics.video_watch_calculator')
    assert hasattr(module,'measure_playback'), 'Speed-aware durable measurement is not implemented'
    return module.measure_playback(events,**kwargs)


def event(kind, second, position):
    return VideoEventInput(kind,NOW+timedelta(seconds=second),position,100.)


def test_speed_adjustment_uses_media_advancement_and_survives_batch_partition():
    events=[event('play_video',0,0),event('play_video',10,20),event('pause_video',50,100)]
    whole=playback(events)
    split=playback(events[1:],previous=playback(events[:1]))
    assert whole==split
    assert whole['media_seconds']==100 and whole['wall_seconds']==50


def test_seek_jump_does_not_count_as_watched_content():
    measurement=playback([event('play_video',0,0),event('seek_video',1,99),event('pause_video',2,100)])
    assert measurement['media_seconds']==1
    assert measurement['observed_intervals']>=1


def test_legacy_progress_cannot_acquire_complete_history_from_new_tail():
    measurement=playback([event('play_video',0,90),event('pause_video',10,100)], historical_data=True)
    assert measurement['complete_history'] is False


def test_missing_position_and_impossible_rate_are_not_accepted_as_coverage():
    missing=playback([event('play_video',0,None),event('pause_video',10,100)])
    assert missing['unknown_intervals']>0
    jump=playback([event('play_video',0,0),event('pause_video',1,100)])
    assert jump['media_seconds']==0


def test_distinct_simultaneous_seek_is_preserved_in_whole_and_split_batches():
    events=[event('play_video',0,0),event('seek_video',0,90),event('pause_video',30,100)]
    whole=playback(events)
    split=playback(events[1:],previous=playback(events[:1]))
    assert whole['media_seconds']==10. and whole==split


def test_orphan_initial_pause_cannot_supply_complete_feature_history():
    measurement=playback([event('pause_video',0,90),event('play_video',1,90),event('pause_video',11,100)])
    assert measurement['complete_history'] is False
    videos=[measured(index=j) for j in range(3)]
    for v in videos:v['evidence_json']['playback_measurement']=measurement
    assert features(videos).row is None


def test_first_observed_play_in_middle_does_not_invent_preceding_history():
    measurement=playback([event('play_video',0,90),event('pause_video',10,100)])
    assert measurement['complete_history'] is False


@pytest.mark.parametrize('missing_start',[False,True])
def test_simultaneous_seek_arriving_later_is_materialized_without_loki_watermark(monkeypatch,missing_start):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.learning_analytics import (AnalyticsTrackingEvent,AnalyticsMaterializedEventReceipt,AnalyticsStudentVideoProgress)
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    engine=create_engine('sqlite://')
    for model in (AnalyticsTrackingEvent,AnalyticsMaterializedEventReceipt,AnalyticsStudentVideoProgress):model.__table__.create(engine)
    with Session(engine) as db:
        service=LearningAnalyticsCoreService(db)
        monkeypatch.setattr(service,'_video_session_lookup',lambda **_: {})
        events=([('pause_video',0,90),('play_video',1,90),('pause_video',11,100)] if missing_start
            else [('play_video',0,0),('seek_video',0,90),('pause_video',30,100)])
        for index,(kind,second,position) in enumerate(events):
            db.add(AnalyticsTrackingEvent(raw_line_hash=f'{index}-{kind}',course_id='c',username='u',video_id='v',
                event_type=kind,event_time=NOW+timedelta(seconds=second),current_time_seconds=position,video_duration_seconds=100.))
            db.commit();service.recalculate_course_video_progress(course_id='c',username='u')
        row=db.query(AnalyticsStudentVideoProgress).one()
        assert row.evidence_json['playback_measurement']['media_seconds']==10.
        assert row.evidence_json['playback_measurement']['complete_history'] is (not missing_start)
        original=row.evidence_json
        service.recalculate_course_video_progress(course_id='c',username='u')
        assert row.evidence_json==original
    engine.dispose()


def test_companion_stop_after_measured_pause_does_not_invalidate_history():
    measurement=playback([event('play_video',0,0),event('pause_video',50,100),event('edx.video.paused',50,100)])
    assert measurement['complete_history'] is True and measurement['media_seconds']==100.


def test_injected_low_coverage_students_lead_both_rankings_and_seed_top_five_is_stable():
    data=cohort(300)
    fake={f'injected-{j}' for j in range(5)}
    data += [MLFeatureRow(f'injected-{j}','video','same',{
        'completion_watch_gap':.98-j*.001, 'watch_ratio':.02+j*.001,
        'seeks_per_watch_minute':.8, 'passive_ratio':.1},NOW) for j in range(5)]
    tops=[]
    for seed in (0,1,7,42,99):
        scores=score_cohorts(data,seed=seed)
        for key in ('baseline_score','comparison_score'):
            top={r.subject_key for r in sorted(data,key=lambda r:-scores[result_key(r)][key])[:5]}
            assert top==fake
            if key=='comparison_score':tops.append(top)
    assert min(len(a&b)/5 for a,b in combinations(tops,2))>=.8


def test_mad_ties_have_equal_relative_percentiles_and_zero_mad_has_finite_scale():
    data=[MLFeatureRow(str(i),'video','c',{'watch_ratio':.8,'completion_watch_gap':.1},NOW) for i in range(30)]
    data.append(MLFeatureRow('low','video','c',{'watch_ratio':.01,'completion_watch_gap':.99},NOW))
    scores=score_cohorts(data)
    assert len({scores[result_key(r)]['reference_percentile'] for r in data[:-1]})==1
    assert scores[result_key(data[-1])]['baseline_score']>scores[result_key(data[0])]['baseline_score']


def test_comparison_fit_failure_preserves_valid_explainable_baseline(monkeypatch):
    from sklearn.ensemble import IsolationForest
    def fail(*args,**kwargs):raise ValueError('unavailable')
    monkeypatch.setattr(IsolationForest,'fit',fail)
    scores=score_cohorts(cohort())
    assert all(s['status']=='SCORED' and s['comparison_status']=='UNAVAILABLE' for s in scores.values())
    assert all(s['reference_percentile'] is not None for s in scores.values())


@pytest.mark.parametrize('legacy', [False,True])
def test_materializer_persists_speed_measurement_across_batches_without_double_counting(monkeypatch,legacy):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.learning_analytics import (AnalyticsTrackingEvent,
        AnalyticsMaterializedEventReceipt, AnalyticsStudentVideoProgress)
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    engine=create_engine('sqlite://')
    for model in (AnalyticsTrackingEvent,AnalyticsMaterializedEventReceipt,AnalyticsStudentVideoProgress):
        model.__table__.create(engine)
    with Session(engine) as db:
        if legacy:
            db.add(AnalyticsStudentVideoProgress(course_id='c',username='u',video_id='v',
                last_event_at=NOW-timedelta(seconds=1),estimated_watch_seconds=10.,evidence_json={}))
        db.add(AnalyticsTrackingEvent(raw_line_hash='start',course_id='c',username='u',video_id='v',
            event_type='play_video',event_time=NOW,current_time_seconds=0.,video_duration_seconds=100.))
        db.commit()
        service=LearningAnalyticsCoreService(db)
        monkeypatch.setattr(service,'_video_session_lookup',lambda **_: {})
        service.recalculate_course_video_progress(course_id='c',username='u')
        db.add(AnalyticsTrackingEvent(raw_line_hash='stop',course_id='c',username='u',video_id='v',
            event_type='pause_video',event_time=NOW+timedelta(seconds=50),
            current_time_seconds=100.,video_duration_seconds=100.))
        db.commit()
        service.recalculate_course_video_progress(course_id='c',username='u')
        row=db.query(AnalyticsStudentVideoProgress).one()
        measurement=row.evidence_json['playback_measurement']
        assert measurement['media_seconds']==100. and measurement['wall_seconds']==50.
        assert measurement['complete_history'] is (not legacy)
        service.recalculate_course_video_progress(course_id='c',username='u')
        assert row.evidence_json['playback_measurement']==measurement
    engine.dispose()
