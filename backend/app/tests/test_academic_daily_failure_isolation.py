"""Daily failures stop dependent targets while preserving independent results."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (AcademicBulkOperationJob, AcademicClass, AcademicClassSyncJob,
                                AcademicSyncRun, AcademicTeacherReportJob, AcademicTerm)
from app.services.academic import daily_academic_pipeline as runtime


class FakeCelery:
    def __init__(self):
        self.sent = []

    def send_task(self, name, args=None, **options):
        self.sent.append((name, args, options))
        return SimpleNamespace(id=f'task-{len(self.sent)}')


@pytest.fixture
def db_factory(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:',
                           connect_args={'check_same_thread': False}, poolclass=StaticPool)
    for model in (AcademicTerm, AcademicClass, AcademicBulkOperationJob,
                  AcademicClassSyncJob, AcademicSyncRun, AcademicTeacherReportJob):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    yield factory
    engine.dispose()


def seed(db, stage, *, round_no=3):
    scopes = []
    for branch, names in (('poly', ['other']), ('ptcd', ['good', 'bad', 'bad-2'])):
        scope = {'scope_key': f'{branch}:term-{branch}', 'term_id': f'term-{branch}',
                 'term_name': 'Fall 2026', 'branch': branch,
                 'campuses': ['hn'] if branch == 'poly' else ['hcm', 'dn'],
                 'class_ids': [f'class-{name}' for name in names],
                 'subject_ids': sorted({f'subject-{name if name != "bad-2" else "bad"}' for name in names}),
                 'class_to_campus': {f'class-{name}': 'hn' if branch == 'poly' else
                                     ('dn' if name == 'good' else 'hcm') for name in names},
                 'scope_hash': f'hash-{branch}'}
        scopes.append(scope)
        db.add(AcademicTerm(id=scope['term_id'], branch=branch, term_code='FA26', term_name='Fall'))
        for name in names:
            db.add(AcademicClass(id=f'class-{name}', term_id=scope['term_id'],
                                subject_id=f'subject-{name if name != "bad-2" else "bad"}',
                                class_code=f'CODE-{name}', campus=scope['class_to_campus'][f'class-{name}'],
                                branch=branch, active=True))
    targets = ([s['scope_key'] for s in scopes] if stage in {'ap_sync', 'course_mapping', 'campus_snapshots', 'ho_snapshots', 'ho_reports'}
               else runtime._campus_targets(scopes) if stage == 'campus_reports'
               else runtime._round_robin_class_targets(scopes))
    state = {'phase': stage, 'stage_round': round_no, 'stage_target_keys': targets,
             'attempts_by_stage': {}, 'frozen_scopes_after_ap': {s['scope_key']: s for s in scopes},
             'artifacts': {}, 'source_synced_at': datetime.utcnow().isoformat(),
             'campus_snapshot_ids_by_target': {t: f'snapshot-{t}' for t in runtime._campus_targets(scopes)},
             'ho_snapshot_ids_by_scope': {s['scope_key']: f'ho-{s["branch"]}' for s in scopes}}
    root = AcademicBulkOperationJob(id='root', job_type=runtime.DAILY_ROOT_JOB_TYPE, status='running',
                                   request_json={'scopes': scopes, 'run_date_vn': '2026-11-12'}, result_json=state)
    db.add(root)
    db.commit()
    runtime.ensure_scope_parents(db, root, scopes)
    return root, scopes, state


def attempts(db, root, state, statuses, *, mapping_result=None):
    stage = state['phase']
    ids = {}
    for target in state['stage_target_keys']:
        status = statuses.get(target, 'completed')
        model = runtime._attempt_model_for_stage(stage)
        values = dict(id=f'attempt-{target}', status=status, error_message='PSY1013: no unique CMS course' if status == 'failed' else None)
        if model == AcademicSyncRun:
            values.update(source='ap', mode='api_all_job', term_name='Fall', counters_json={})
        else:
            values.update(request_json={}, result_json={}, parent_job_id=root.id)
            if stage == 'course_mapping' and status == 'completed':
                values['result_json'] = {'mapped_class_ids': state['frozen_scopes_after_ap'][target]['class_ids'],
                                         'failed_class_ids': []}
            if model == AcademicClassSyncJob:
                values.update(class_id=target, job_type='learning_sync' if stage == 'score_update' else 'full_cms_sync')
            else:
                values.update(job_type='test-attempt')
        if mapping_result and target == 'ptcd:term-ptcd':
            values['result_json'] = mapping_result
        db.add(model(**values))
        ids[target] = values['id']
    state['attempts_by_stage'] = {stage: {str(state['stage_round']): ids}}
    root.result_json = state
    db.commit()


def partial_mapping():
    return {'mapped_class_ids': ['class-good'], 'failed_class_ids': ['class-bad', 'class-bad-2'],
            'subject_failed': 1, 'subject_results': [
                {'subject_id': 'subject-good', 'class_ids': ['class-good'], 'ok': True},
                {'subject_id': 'subject-bad', 'subject_code': 'PSY1013', 'class_ids': ['class-bad', 'class-bad-2'],
                 'ok': False, 'message': 'no unique CMS course'}]}


def test_mapping_exhaustion_advances_only_explicitly_mapped_classes(db_factory):
    with db_factory() as db:
        root, scopes, state = seed(db, 'course_mapping')
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'}, mapping_result=partial_mapping())
    result = runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    assert result['phase'] == 'account_enrollment'
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running'
        assert set(root.result_json['stage_target_keys']) == {'class-good', 'class-other'}
        assert root.result_json['frozen_scopes_after_ap'] == {s['scope_key']: s for s in scopes}
        assert 'PSY1013' in root.result_json['failure_details'][0]['message']
        assert set(root.result_json['blocked_class_ids_by_stage']['course_mapping']) == {'class-bad', 'class-bad-2'}


def test_mapping_retry_is_narrowed_and_successes_survive_coordinator_reentry(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'course_mapping', round_no=0)
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'}, mapping_result=partial_mapping())
    celery = FakeCelery()
    result = runtime.run_daily_academic_pipeline(celery, 'root')
    assert result['status'] == 'retrying_stage'
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        retry_id = root.result_json['attempts_by_stage']['course_mapping']['1']['ptcd:term-ptcd']
        retry = db.get(AcademicBulkOperationJob, retry_id)
        assert set(retry.request_json['approved_class_ids']) == {'class-bad', 'class-bad-2'}
        assert retry.request_json['approved_subject_ids'] == ['subject-bad']
        original_request = dict(retry.request_json)
    runtime.run_daily_academic_pipeline(celery, 'root')
    with db_factory() as db:
        retry = db.get(AcademicBulkOperationJob, retry_id)
        assert retry.request_json == original_request
        retry.status = 'completed'
        retry.result_json = {'mapped_class_ids': ['class-bad', 'class-bad-2'], 'failed_class_ids': []}
        db.commit()
    runtime.run_daily_academic_pipeline(celery, 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert set(root.result_json['stage_target_keys']) == {'class-good', 'class-other', 'class-bad', 'class-bad-2'}
        assert not root.result_json.get('failure_details')
        assert len([s for s in celery.sent if s[0] == 'academic_subject_auto_map_all_sync_task']) == 1


@pytest.mark.parametrize('result', [{}, {'mapped_class_ids': ['class-good', 'outside'], 'failed_class_ids': ['class-bad', 'class-bad-2']},
                                     {'mapped_class_ids': ['class-good'], 'failed_class_ids': ['class-good', 'class-bad', 'class-bad-2']}])
def test_unverifiable_mapping_failure_stops_only_its_own_scope(db_factory, result):
    with db_factory() as db:
        root, _, state = seed(db, 'course_mapping')
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'}, mapping_result=result)
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running'
        assert root.result_json['stage_target_keys'] == ['class-other']


def test_exhausted_provisioning_class_does_not_stop_other_scores(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'account_enrollment')
        attempts(db, root, state, {'class-bad': 'failed'})
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        scores = db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.job_type == 'learning_sync').all()
        assert {j.class_id for j in scores} == {'class-good', 'class-other', 'class-bad-2'}
        assert db.get(AcademicBulkOperationJob, 'root').status == 'running'


def test_score_failure_suppresses_only_dependent_campus_report_inputs(db_factory):
    with db_factory() as db:
        root, scopes, state = seed(db, 'score_update')
        attempts(db, root, state, {'class-bad': 'failed'})
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        reports = root.result_json['reporting_scopes']
        assert reports['poly:term-poly'] == scopes[0]
        assert reports['ptcd:term-ptcd']['campuses'] == ['dn']
        assert reports['ptcd:term-ptcd']['class_ids'] == ['class-good']
        assert reports['ptcd:term-ptcd']['scope_hash'] != scopes[1]['scope_hash']
        assert root.result_json['skipped_report_targets']


def test_snapshot_exhaustion_keeps_successful_branch_reports_running(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'campus_snapshots')
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'})
        good = db.get(AcademicBulkOperationJob, 'attempt-poly:term-poly')
        good.result_json = {'snapshot_ids_by_campus': {'hn': 'snapshot-good'}}
        db.commit()
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        exports = db.query(AcademicTeacherReportJob).all()
        assert len(exports) == 1
        assert exports[0].branch == 'poly'
        assert db.get(AcademicBulkOperationJob, 'root').status == 'running'


def test_campus_report_failure_does_not_stop_unrelated_ho_snapshot(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'campus_reports')
        attempts(db, root, state, {'ptcd:term-ptcd:hcm': 'failed'})
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        snapshots = db.query(AcademicBulkOperationJob).filter(AcademicBulkOperationJob.job_type == 'daily_report_snapshot_attempt').all()
        assert len(snapshots) == 1
        assert snapshots[0].branch == 'poly'
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running'
        assert len(root.result_json['artifacts']['campus_reports']) == 2


def test_partial_run_finishes_failed_with_artifacts_and_scope_specific_outcomes(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'ho_reports')
        state['failure_details'] = [{'stage': 'course_mapping', 'target_key': 'ptcd:term-ptcd',
                                    'scope_key': 'ptcd:term-ptcd', 'class_ids': ['class-bad'],
                                    'attempt_id': 'mapping-failed', 'message': 'PSY1013: no unique CMS course'}]
        state['failures_by_stage'] = {'course_mapping': ['ptcd:term-ptcd']}
        state['stage_target_keys'] = ['poly:term-poly']
        state['artifacts'] = {'campus_reports': {'poly:term-poly:hn': 'campus-good'}}
        attempts(db, root, state, {})
    celery = FakeCelery()
    result = runtime.run_daily_academic_pipeline(celery, 'root')
    assert result['ok'] is False
    assert result['partial_success'] is True
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'failed'
        assert root.result_json['processing_complete'] is True
        assert root.result_json['artifacts']['campus_reports']['poly:term-poly:hn'] == 'campus-good'
        assert 'PSY1013' in root.error_message
        parents = db.query(AcademicBulkOperationJob).filter(AcademicBulkOperationJob.parent_job_id == root.id,
                    AcademicBulkOperationJob.job_type.in_(['academic_daily_provision_scope', 'academic_daily_score-report_scope'])).all()
        assert {p.status for p in parents if p.branch == 'poly'} == {'completed'}
        assert {p.status for p in parents if p.branch == 'ptcd'} == {'failed'}
    assert runtime.run_daily_academic_pipeline(celery, 'root')['status'] == 'failed'
    assert not celery.sent


def test_ap_exhaustion_allows_successful_branch_mapping(db_factory, monkeypatch):
    with db_factory() as db:
        root, _, state = seed(db, 'ap_sync')
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'})
    monkeypatch.setattr(runtime, '_refresh_scope_after_ap', lambda db, scope: dict(scope))
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        mappings = db.query(AcademicBulkOperationJob).filter(AcademicBulkOperationJob.job_type == 'subject_auto_map_all_sync').all()
        assert len(mappings) == 1
        assert mappings[0].branch == 'poly'
        assert db.get(AcademicBulkOperationJob, 'root').status == 'running'


def test_completed_mapping_with_invalid_partition_cannot_be_silent_success(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'course_mapping')
        attempts(db, root, state, {}, mapping_result={'mapped_class_ids': ['outside'], 'failed_class_ids': []})
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.result_json['stage_target_keys'] == ['class-other']
        assert root.result_json['failure_details'][0]['scope_key'] == 'ptcd:term-ptcd'
        assert 'partition' in root.result_json['failure_details'][0]['message']


def test_mixed_mapping_run_keeps_independent_artifacts_and_never_dispatches_failed_classes(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'course_mapping')
        attempts(db, root, state, {'ptcd:term-ptcd': 'failed'}, mapping_result=partial_mapping())
    celery = FakeCelery()
    for _ in range(12):
        result = runtime.run_daily_academic_pipeline(celery, 'root')
        with db_factory() as db:
            root = db.get(AcademicBulkOperationJob, 'root')
            if root.status == 'failed':
                break
            for job in db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.status == 'queued').all():
                assert job.class_id in {'class-good', 'class-other'}
                job.status = 'completed'
                job.finished_at = datetime.utcnow()
            for job in db.query(AcademicBulkOperationJob).filter(AcademicBulkOperationJob.job_type == 'daily_report_snapshot_attempt',
                                                                 AcademicBulkOperationJob.status == 'queued').all():
                scope = job.request_json['scope']
                if job.request_json['snapshot_type'] == 'campus_set':
                    assert scope['campuses'] in (['hn'], ['dn'])
                    job.result_json = {'snapshot_ids_by_campus': {campus: f'snap-{scope["branch"]}-{campus}' for campus in scope['campuses']}}
                else:
                    assert scope['branch'] == 'poly'
                    job.result_json = {'ho_snapshot_id': 'ho-poly'}
                job.status = 'completed'
            for job in db.query(AcademicTeacherReportJob).filter(AcademicTeacherReportJob.status == 'queued').all():
                job.status = 'completed'
            db.commit()
    else:
        pytest.fail('coordinator never finalized independent work')
    assert result['ok'] is False
    assert result['partial_success'] is True
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert set(root.result_json['artifacts']['campus_reports']) == {'poly:term-poly:hn', 'ptcd:term-ptcd:dn'}
        assert set(root.result_json['artifacts']['ho_reports']) == {'poly:term-poly'}
        assert root.result_json['failure_details'][0]['subject_failures'][0]['subject_code'] == 'PSY1013'
        assert 'PSY1013' in root.error_message
        assert set(root.result_json['score_job_ids_by_class']) == {'class-good', 'class-other'}


def test_completed_snapshot_missing_campus_cannot_hide_failed_report_inputs(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'campus_snapshots')
        attempts(db, root, state, {})
        db.get(AcademicBulkOperationJob, 'attempt-poly:term-poly').result_json = {'snapshot_ids_by_campus': {'hn': 'poly-snapshot'}}
        db.get(AcademicBulkOperationJob, 'attempt-ptcd:term-ptcd').result_json = {'snapshot_ids_by_campus': {'dn': 'ptcd-snapshot'}}
        db.commit()
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.result_json['failure_details'][0]['scope_key'] == 'ptcd:term-ptcd'
        assert 'snapshot' in root.result_json['failure_details'][0]['message']
        reports = db.query(AcademicTeacherReportJob).all()
        assert len(reports) == 1
        assert reports[0].branch == 'poly'


def test_all_failed_ap_scopes_finish_failed_without_phantom_reports(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'ap_sync')
        attempts(db, root, state, {key: 'failed' for key in state['stage_target_keys']})
    celery = FakeCelery()
    for _ in range(5):
        result = runtime.run_daily_academic_pipeline(celery, 'root')
        if result['status'] == 'failed':
            break
    else:
        pytest.fail('empty independent pipeline did not finish')
    assert result['ok'] is False
    assert result['partial_success'] is False
    with db_factory() as db:
        assert not db.query(AcademicClassSyncJob).all()
        assert not db.query(AcademicTeacherReportJob).all()
        assert len(db.get(AcademicBulkOperationJob, 'root').result_json['failure_details']) == 2


@pytest.mark.parametrize('stage', ['campus_snapshots', 'ho_snapshots'])
def test_completed_snapshot_with_empty_result_is_retried_before_failure(db_factory, stage):
    with db_factory() as db:
        root, _, state = seed(db, stage, round_no=0)
        attempts(db, root, state, {})
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running'
        assert root.result_json['phase'] == stage
        assert root.result_json['stage_round'] == 1
        retry_ids = root.result_json['attempts_by_stage'][stage]['1']
        assert set(retry_ids) == {'poly:term-poly', 'ptcd:term-ptcd'}
        assert all(db.get(AcademicBulkOperationJob, jid).status == 'queued' for jid in retry_ids.values())
        assert not db.query(AcademicTeacherReportJob).all()


@pytest.mark.parametrize('stage', ['campus_snapshots', 'ho_snapshots'])
def test_completed_snapshot_with_empty_result_finishes_failed_at_retry_limit(db_factory, stage):
    with db_factory() as db:
        root, _, state = seed(db, stage)
        attempts(db, root, state, {})
    result = runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    assert result['status'] == 'failed'
    assert result['ok'] is False
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert len(root.result_json['failure_details']) == 2
        assert all('snapshot' in detail['message'] for detail in root.result_json['failure_details'])
        assert not db.query(AcademicTeacherReportJob).all()


def test_all_failed_ap_scopes_do_not_label_parents_partial_success(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'ap_sync')
        attempts(db, root, state, {key: 'failed' for key in state['stage_target_keys']})
    for _ in range(5):
        result = runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
        if result['status'] == 'failed':
            break
    with db_factory() as db:
        parents = db.query(AcademicBulkOperationJob).filter(AcademicBulkOperationJob.parent_job_id == 'root',
                    AcademicBulkOperationJob.job_type.in_(['academic_daily_provision_scope', 'academic_daily_score-report_scope'])).all()
        assert len(parents) == 4
        assert all(parent.status == 'failed' for parent in parents)
        assert all(parent.result_json.get('partial_success') is False for parent in parents)


def test_completed_mapping_empty_result_does_not_authorize_any_class(db_factory):
    with db_factory() as db:
        root, _, state = seed(db, 'course_mapping')
        attempts(db, root, state, {})
        db.get(AcademicBulkOperationJob, 'attempt-poly:term-poly').result_json = {
            'mapped_class_ids': ['class-other'], 'failed_class_ids': []}
        db.get(AcademicBulkOperationJob, 'attempt-ptcd:term-ptcd').result_json = {}
        db.commit()
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with db_factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.result_json['stage_target_keys'] == ['class-other']
        assert root.result_json['failure_details'][0]['scope_key'] == 'ptcd:term-ptcd'
