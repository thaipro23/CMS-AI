from datetime import datetime, timedelta
from importlib import import_module, util

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import (AcademicClass, AcademicClassCourseMapping, AcademicCourseMapping,
    AcademicClassStudent, AcademicStudent, AcademicStudentLearningSnapshot)
from app.models.learning_analytics import (AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentVideoProgress, AnalyticsQuizAttempt, AnalyticsQuizItemSubmission,
    AnalyticsQuizIntegrityResult, AnalyticsTrackingEvent, AnalyticsQuizItemReceipt)
from app.models.learning_analytics import AnalyticsStudentSessionProgress

NOW = datetime(2026, 10, 9, 8)


def workflow(db):
    name = 'app.services.learning_analytics.ml_workflow'
    assert util.find_spec(name), 'ML worker orchestration is not implemented'
    return import_module(name).LearningMLWorkflow(db)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_mode', 'shadow')
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_pilot_class_ids', 'class')
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_min_reference_students', 50)
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_max_reference_students', 5000)
    engine = create_engine('sqlite://')
    models = (AcademicClass, AcademicClassCourseMapping, AcademicCourseMapping, AcademicClassStudent,
        AcademicStudent, AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
        AnalyticsStudentVideoProgress, AnalyticsQuizAttempt, AnalyticsQuizItemSubmission,
        AnalyticsQuizIntegrityResult, AnalyticsTrackingEvent, AcademicStudentLearningSnapshot,
        AnalyticsStudentSessionProgress, AnalyticsQuizItemReceipt)
    for m in models:
        m.__table__.create(engine)
    with Session(engine) as session:
        session.add(AcademicClass(id='class', term_id='t', subject_id='s', class_code='class', active=True))
        session.add(AcademicClassCourseMapping(class_id='class', openedx_course_id='course', active=True))
        session.add(AnalyticsCourseSession(course_id='course', session_key='lesson', session_index=1,
            active=True, components_json={'components': [{'usage_key': f'v{i}', 'block_type': 'video'} for i in range(3)]}))
        for i in range(55):
            name = f'u{i}'
            session.add(AcademicStudent(id=name, username=name, student_code=name, active=True))
            session.add(AcademicClassStudent(class_id='class', student_id=name))
            session.add(AnalyticsLearningBehaviorSnapshot(class_id='class', course_id='course',
                username=name, calculated_at=NOW, classification='NORMAL', evidence_json={'rule': 'kept'}))
            for j in range(3):
                session.add(AnalyticsStudentVideoProgress(course_id='course', username=name, video_id=f'v{j}',
                    session_index=1, duration_seconds=100, completion_percent=80+i/10,
                    estimated_watch_seconds=70+i/10, passive_watch_seconds=10,
                    seek_count=i%3, last_event_at=NOW-timedelta(seconds=1)))
        session.commit()
        yield session
    engine.dispose()


def call(db, targets):
    return workflow(db).score_behavior(class_id='class', course_id='course', target_usernames=targets, cutoff=NOW)


def result(db, user):
    return db.query(AnalyticsLearningBehaviorSnapshot).filter_by(username=user).one()


def test_single_user_uses_full_reference_pool_and_writes_only_target(db):
    call(db, ['u0'])
    before = result(db, 'u0').evidence_json['ml']
    assert before['status'] == 'SCORED' and before['reference_count'] == 55
    assert result(db, 'u1').evidence_json == {'rule': 'kept'}
    call(db, [f'u{i}' for i in range(55)])
    assert result(db, 'u0').evidence_json['ml']['cohort_digest'] == before['cohort_digest']
    assert result(db, 'u0').classification == 'NORMAL'
    assert result(db, 'u0').evidence_json['rule'] == 'kept'


def test_off_and_nonpilot_do_not_fit_or_load_data(db, monkeypatch):
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_mode', 'off')
    assert call(db, ['u0'])['status'] == 'disabled'
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_mode', 'shadow')
    monkeypatch.setitem(settings.__dict__, 'analytics_ml_pilot_class_ids', '')
    assert call(db, ['u0'])['status'] == 'disabled'
    assert result(db, 'u0').evidence_json == {'rule': 'kept'}


def test_raw_retention_does_not_remove_aggregate_based_ml(db):
    db.query(AnalyticsTrackingEvent).delete()
    call(db, ['u0'])
    assert result(db, 'u0').evidence_json['ml']['status'] == 'SCORED'


def test_unknown_target_does_not_get_a_snapshot(db):
    call(db, ['outsider'])
    assert db.query(AnalyticsLearningBehaviorSnapshot).filter_by(username='outsider').count() == 0


def test_newer_snapshot_is_not_overwritten(db):
    row = result(db, 'u0')
    row.calculated_at = NOW + timedelta(seconds=1)
    row.evidence_json = {'newer': True}
    db.commit()
    call(db, ['u0'])
    assert result(db, 'u0').evidence_json == {'newer': True}


def test_model_exception_preserves_rules_and_official_grade(db, monkeypatch):
    wf = workflow(db)
    db.add(AcademicStudentLearningSnapshot(class_id='class', student_id='u0', openedx_course_id='course',
        grade_percent=83, raw_json={'official': True}))
    db.commit()
    import app.services.learning_analytics.ml_workflow as module
    def fail(*args, **kwargs):
        raise RuntimeError('simulated fit failure')
    monkeypatch.setattr(module, 'score_cohorts', fail)
    assert wf.score_behavior(class_id='class', course_id='course', target_usernames=['u0'], cutoff=NOW)['status'] == 'error'
    assert result(db, 'u0').classification == 'NORMAL'
    official = db.query(AcademicStudentLearningSnapshot).one()
    assert official.grade_percent == 83 and official.raw_json == {'official': True}


def test_fit_once_for_the_cohort(db, monkeypatch):
    wf = workflow(db)
    from sklearn.ensemble import IsolationForest
    original = IsolationForest.fit
    seen = []
    def observed(self, X, *args, **kwargs):
        seen.append(len(X))
        return original(self, X, *args, **kwargs)
    monkeypatch.setattr(IsolationForest, 'fit', observed)
    wf.score_behavior(class_id='class', course_id='course', target_usernames=[f'u{i}' for i in range(55)], cutoff=NOW)
    assert seen == [55]


def seed_quiz_history(db):
    from datetime import timedelta
    for i in range(55):
        name = f'u{i}'
        start = NOW-timedelta(seconds=1000)
        times = [start+timedelta(seconds=(j+1)*(60+i)) for j in range(6)]
        db.add(AnalyticsQuizAttempt(id='a'+name, course_id='course', username=name,
            unit_usage_key='quiz', attempt_no=1, unit_reset_nonce=f'quiz-session:{i}',
            started_at=start, ended_at=NOW, submission_count=6,
            evidence_json={'start_observed': True, 'session_event_provenance': 'server_quiz_session_v1',
            'submission_timing_provenance':'server_submissions_v1',
            'reset_event_provenance':'server_reset_new_session_v1', 'successful_reset_times':[],
                'server_submission_times': [{'problem_usage_key': f'p{j}', 'submitted_at': t.isoformat()} for j, t in enumerate(times)]}))
        db.add(AnalyticsQuizIntegrityResult(class_id='class', course_id='course', username=name,
            unit_usage_key='quiz', status='INSUFFICIENT_DATA', calculated_at=NOW, evidence_json={'rule': True}))
        for j, t in enumerate(times):
            db.add(AnalyticsQuizItemSubmission(event_fingerprint=f'{name}-{j}', attempt_id='a'+name,
                course_id='course', username=name, unit_usage_key='quiz', problem_usage_key=f'p{j}',
                input_id=f'p{j}_1_1', input_slot='_1_1', variant='', submitted_at=t,
                content_version='sha256:'+'a'*64, question_hash=f'{j:064x}'))
    db.commit()


def test_quiz_uses_persisted_attempt_items_and_preserves_rule_status(db):
    seed_quiz_history(db)
    workflow(db).score_quiz(class_id='class', course_id='course', target_usernames=['u0'], cutoff=NOW)
    row = db.query(AnalyticsQuizIntegrityResult).filter_by(username='u0').one()
    assert row.evidence_json['ml']['status'] == 'SCORED'
    assert row.evidence_json['ml']['reference_count'] == 55
    assert row.status == 'INSUFFICIENT_DATA' and row.evidence_json['rule'] is True
    assert 'ml' not in db.query(AnalyticsQuizIntegrityResult).filter_by(username='u1').one().evidence_json


def test_cancellation_stops_before_loading_or_writing(db):
    wf = workflow(db)
    wf.cancelled = lambda: True
    assert wf.score_behavior(class_id='class', course_id='course', target_usernames=['u0'], cutoff=NOW)['status'] == 'cancelled'
    assert result(db, 'u0').evidence_json == {'rule': 'kept'}


def test_recalculate_behavior_can_defer_ml_in_student_loop(db, monkeypatch):
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    cls = type(workflow(db))
    def unexpected(*args, **kwargs):
        raise AssertionError('Must not fit inside the worker student loop')
    monkeypatch.setattr(cls, 'score_behavior', unexpected)
    result_ = LearningAnalyticsCoreService(db).recalculate_learning_behavior(class_id=None,
        course_id='course', username='u0', refresh_session_progress=False, refresh_ml=False)
    assert result_['processed'] == 1
    assert result_['ml']['status'] == 'deferred'


def test_cached_snapshot_cannot_overwrite_more_recent_ml(db):
    from sqlalchemy import update
    row = result(db, 'u0')
    # Another transaction writes ML while this Session still holds an older object.
    db.execute(update(AnalyticsLearningBehaviorSnapshot).where(
        AnalyticsLearningBehaviorSnapshot.id == row.id).values(evidence_json={
            'rule': 'new', 'ml': {'cutoff': (NOW+timedelta(seconds=1)).isoformat()}}),
        execution_options={'synchronize_session': False})
    call(db, ['u0'])
    db.expire(row)
    assert row.evidence_json['rule'] == 'new'
    assert row.evidence_json['ml']['cutoff'] == (NOW+timedelta(seconds=1)).isoformat()


def test_removed_videos_are_not_compared_as_current_outline(db):
    outline = db.query(AnalyticsCourseSession).one()
    outline.components_json = {'components': [{'usage_key': 'different', 'block_type': 'video'}]}
    db.commit()
    call(db, ['u0'])
    assert result(db, 'u0').evidence_json['ml']['status'] == 'INSUFFICIENT_DATA'


def test_single_user_quiz_recalculate_does_not_write_other_learners_ml(db, monkeypatch):
    from copy import deepcopy
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    seed_quiz_history(db)
    untouched = db.query(AnalyticsQuizIntegrityResult).filter_by(username='u1').one()
    untouched.evidence_json = {'rule': True, 'ml': {'preserved': True}}
    db.add(AnalyticsQuizIntegrityResult(class_id='class', course_id='course', username='u1',
        unit_usage_key='legacy', calculated_at=NOW, evidence_json={'alias': True, 'ml': {'preserved': True}}))
    db.commit()
    before = {r.id: (deepcopy(r.evidence_json), r.calculated_at) for r in db.query(AnalyticsQuizIntegrityResult).filter_by(username='u1')}
    monkeypatch.setattr(settings, 'analytics_quiz_integrity_enabled', True)
    service = LearningAnalyticsCoreService(db)
    monkeypatch.setattr(service, '_class_tracking_identity_maps', lambda **_: {'ap_usernames': [f'u{i}' for i in range(55)]})
    monkeypatch.setattr(service, '_quiz_unit_aliases', lambda _: {'legacy':'quiz'})
    outcome = service.recalculate_class_quiz_integrity(class_id='class', course_id='course', target_usernames=['u0'])
    assert outcome['status']=='completed' and outcome['results']==1
    after = {r.id: (r.evidence_json, r.calculated_at) for r in db.query(AnalyticsQuizIntegrityResult).filter_by(username='u1').populate_existing()}
    assert after==before
    assert db.query(AnalyticsQuizIntegrityResult).filter_by(username='u0').one().evidence_json['ml']['status'] == 'SCORED'


def test_bare_video_block_ids_match_current_full_usage_keys(db):
    outline = db.query(AnalyticsCourseSession).one()
    outline.components_json = {'components': [{'usage_key': f'block-v1:ORG+COURSE+RUN+type@video+block@v{i}', 'block_type': 'video'} for i in range(3)]}
    db.commit()
    call(db, ['u0'])
    assert result(db, 'u0').evidence_json['ml']['status'] == 'SCORED'


def test_first_eligible_attempt_is_selected_per_content_cohort(db, monkeypatch):
    seed_quiz_history(db)
    from sklearn.ensemble import IsolationForest
    seen=[]
    original=IsolationForest.fit
    def fit(self, X, *args, **kwargs):
        seen.append(len(X))
        return original(self,X,*args,**kwargs)
    monkeypatch.setattr(IsolationForest,'fit',fit)
    start=NOW+timedelta(seconds=10)
    for i in range(55):
        user=f'u{i}'; times=[start+timedelta(seconds=(j+1)*(30+i)) for j in range(6)]
        db.add(AnalyticsQuizAttempt(id='b'+user, course_id='course', username=user, unit_usage_key='quiz',
            attempt_no=2, unit_reset_nonce='quiz-session:b'+user, started_at=start, ended_at=NOW+timedelta(seconds=900),
            evidence_json={'start_observed':True,'session_event_provenance':'server_quiz_session_v1',
                'submission_timing_provenance':'server_submissions_v1','reset_event_provenance':'server_reset_new_session_v1',
                'successful_reset_times':[], 'server_submission_times':[{'problem_usage_key':f'p{j}','submitted_at':t.isoformat()} for j,t in enumerate(times)]}))
        for j,t in enumerate(times):
            db.add(AnalyticsQuizItemSubmission(event_fingerprint=f'b-{user}-{j}',attempt_id='b'+user,
                course_id='course',username=user,unit_usage_key='quiz',problem_usage_key=f'p{j}',input_id=f'p{j}_1_1',
                input_slot='_1_1',variant='',submitted_at=t,content_version='sha256:'+'b'*64,question_hash=f'{j:064x}'))
    db.commit()
    outcome=workflow(db).score_quiz(class_id='class',course_id='course',target_usernames=['u0'],cutoff=NOW+timedelta(seconds=1000))
    assert outcome['status']=='completed'
    assert sorted(seen)==[55,55]
    analysis=db.query(AnalyticsQuizIntegrityResult).filter_by(username='u0').one().evidence_json['ml']
    assert analysis['reference_count']==55 and analysis['features']['seconds_per_independent_submission']==30
