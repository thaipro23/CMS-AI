from dataclasses import replace

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import event, update

from app.core.config import Settings, settings
from app.core.rbac import UserContext
from app.core.redis_client import get_redis_client
from app.models.academic import AcademicStudentLearningSnapshot
from app.services.academic import teacher_report_cache as cache
from app.services.academic.helpers import AccessDecision
from app.services.academic_service import AcademicService
from app.tests.test_teacher_cms_list_performance import seeded_report


class MemoryRedis:
    def __init__(self):
        self.data, self.ttls = {}, {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        if ex:
            self.ttls[key] = ex
        return True


@pytest.fixture
def store(monkeypatch):
    client = MemoryRedis()
    monkeypatch.setattr(cache, 'get_redis_client', lambda **kwargs: client)
    monkeypatch.setattr(settings, 'teacher_report_cache_ttl_seconds', 45)
    return client


def overview(db, **kwargs):
    return AcademicService(db).training_teacher_report(
        UserContext(user_id='admin', role='admin', permissions={'manage_settings'},
                    raw_claims={'ai_system_admin': True}),
        term_id='term', branch='poly', learning_platform='cms', page_size=15, **kwargs)


def test_cache_hit_skips_report_queries_and_keeps_numbers(store):
    with seeded_report(20) as db:
        first = overview(db)
        statements = []
        listener = lambda _c, _cur, sql, *_: statements.append(sql)
        event.listen(db.bind, 'before_cursor_execute', listener)
        second = overview(db)
        event.remove(db.bind, 'before_cursor_execute', listener)
        assert first['items'] == second['items']
        assert first['summary'] == second['summary']
        assert second['cache']['redis_status'] == 'hit'
        assert not any('academic_student_learning_snapshots' in sql for sql in statements)
        assert not any('academic_teacher_report_summaries' in sql for sql in statements)
        assert set(store.ttls.values()) == {45}


def test_page_and_filter_are_separate_cache_entries(store):
    with seeded_report(20) as db:
        first, second = overview(db), overview(db, page=2)
        assert len(first['items']) == 15 and len(second['items']) == 5
        assert overview(db, search='teacher-019')['total'] == 1
        assert overview(db)['total'] == 20


def test_fresh_read_bypasses_cache_without_poisoning_it(store):
    with seeded_report() as db:
        overview(db)
        old = dict(store.data)
        fresh = overview(db, use_cache=False)
        assert fresh['cache'].get('redis_status') != 'hit'
        assert store.data == old


@pytest.mark.parametrize('mode', ['orm', 'execute', 'bulk'])
def test_committed_snapshot_change_invalidates_page(store, mode):
    with seeded_report() as db:
        assert overview(db)['items'][0]['learning_avg_progress_percent'] == 98
        if mode == 'orm':
            db.get(AcademicStudentLearningSnapshot, 'snapshot-0-0').progress_percent = 100
        elif mode == 'execute':
            db.execute(update(AcademicStudentLearningSnapshot).values(progress_percent=100))
        else:
            db.query(AcademicStudentLearningSnapshot).update({'progress_percent': 100})
        db.commit()
        result = overview(db)
        assert result['items'][0]['learning_avg_progress_percent'] == 100
        assert result['cache']['redis_status'] == 'miss'


def test_rollback_does_not_invalidate(store):
    with seeded_report() as db:
        overview(db)
        old = dict(store.data)
        db.get(AcademicStudentLearningSnapshot, 'snapshot-0-0').progress_percent = 100
        db.flush()
        db.rollback()
        assert store.data == old
        assert overview(db)['cache']['redis_status'] == 'hit'


def test_redis_outage_and_corrupt_entry_fall_back_to_sql(store, monkeypatch):
    with seeded_report() as db:
        overview(db)
        for key in list(store.data):
            if key != cache.GENERATION_KEY:
                store.data[key] = '{broken'
        assert overview(db)['total'] == 1
        monkeypatch.setattr(store, 'get', lambda *_: (_ for _ in ()).throw(ConnectionError('offline')))
        assert overview(db)['total'] == 1


def test_permission_fingerprint_prevents_stale_scope_hit(store):
    class Workflow:
        calls = 0
        decision = AccessDecision(False, {'one'}, set(), set(), None)

        def access_decision(self, user):
            return self.decision

        @cache.cached_teacher_overview
        def report(self, user, *, term_id=None, **kwargs):
            self.calls += 1
            return {'items': sorted(self.decision.teacher_ids), 'cache': {}}

    workflow = Workflow()
    user = UserContext('viewer', 'viewer', {'academic_view'})
    assert workflow.report(user, term_id='term')['items'] == ['one']
    assert workflow.report(user, term_id='term')['items'] == ['one']
    assert workflow.calls == 1
    workflow.decision = replace(workflow.decision, teacher_ids={'two'})
    assert workflow.report(user, term_id='term')['items'] == ['two']
    assert workflow.calls == 2


def test_cache_miss_uses_the_same_decision_as_its_permission_key(store, monkeypatch):
    decisions = []
    def changing_decision(_self, _user):
        decisions.append(1)
        return (AccessDecision(False, {'teacher-000'}, set(), set(), set())
                if len(decisions) % 2 else AccessDecision(True, set(), set(), set(), None))
    monkeypatch.setattr(AcademicService, 'access_decision', changing_decision)
    with seeded_report(2) as db:
        first = overview(db)
        assert first['total'] == 1
        assert len(decisions) == 1
        assert overview(db)['total'] == 2
        assert len(decisions) == 2
        assert overview(db)['total'] == 1
        assert len(decisions) == 3


def test_pool_is_reused_and_cache_endpoint_is_separate(monkeypatch):
    monkeypatch.setattr(settings, 'redis_url', 'redis://localhost:16379/0')
    monkeypatch.setattr(settings, 'redis_cache_url', 'redis://localhost:16379/1')
    a, b = get_redis_client(), get_redis_client()
    assert a.connection_pool is b.connection_pool
    c = get_redis_client(cache=True)
    assert c.connection_pool is not a.connection_pool
    assert c.connection_pool.connection_kwargs['db'] == 1
    assert a.connection_pool.connection_kwargs['socket_timeout'] <= 1
    a.close()
    assert b.connection_pool is get_redis_client().connection_pool


def test_pool_is_not_shared_across_processes(monkeypatch):
    from app.core import redis_client
    original = get_redis_client().connection_pool
    monkeypatch.setattr(redis_client.os, 'getpid', lambda: 999999)
    assert get_redis_client().connection_pool is not original


def test_evicted_generation_does_not_resurrect_old_pages(store):
    with seeded_report() as db:
        overview(db)
        old_token = store.data.pop(cache.GENERATION_KEY)
        result = overview(db)
        assert result['cache']['redis_status'] == 'miss'
        assert store.data[cache.GENERATION_KEY] != old_token


def test_nested_commit_does_not_invalidate_before_outer_commit(store):
    with seeded_report() as db:
        overview(db)
        old = store.data[cache.GENERATION_KEY]
        with db.begin_nested():
            db.get(AcademicStudentLearningSnapshot, 'snapshot-0-0').progress_percent = 100
        assert store.data[cache.GENERATION_KEY] == old
        db.commit()
        assert store.data[cache.GENERATION_KEY] != old


def test_snapshot_rebuild_invalidates_postgres_summary_pages(store):
    from app.models.academic import AcademicTeacherReportSummary
    with seeded_report() as db:
        overview(db)
        old = store.data[cache.GENERATION_KEY]
        db.add(AcademicTeacherReportSummary(scope_key='scope', term_id='term', teacher_id='teacher-000',
                                          teacher_username='teacher-000', teacher_name='Name'))
        db.commit()
        assert store.data[cache.GENERATION_KEY] != old


def test_separate_cache_credentials_do_not_inherit_broker_password():
    conf = Settings(_env_file=None, redis_url='redis://broker/0', redis_password='broker-secret',
                    redis_cache_url='redis://cache/0', redis_cache_password='cache-secret')
    assert 'broker-secret@broker' in conf.redis_url
    assert 'cache-secret@cache' in conf.redis_cache_url
