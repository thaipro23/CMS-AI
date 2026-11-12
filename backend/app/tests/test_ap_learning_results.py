import hashlib
import json
from datetime import datetime, timedelta
from importlib import import_module, util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import get_db
from app.models.academic import (AcademicBlock, AcademicClass, AcademicClassCourseMapping,
    AcademicClassStudent, AcademicCourseMapping, AcademicStudent, AcademicSubject, AcademicTerm)
from app.models.learning_analytics import AnalyticsLearningBehaviorSnapshot as Snapshot
from app.services.learning_analytics.learning_behavior_classifier import SCORING_VERSION

KEY = 'test-key-with-more-than-thirty-two-bytes-12345'
COURSE = 'course-v1:FPL+WEB3023+FA26'
BASE = '/api/integrations/ap/v1/classes/ap-class'
PARAMS = dict(branch='poly', campus='HN', ap_term_id='ap-term', subject_code='WEB3023')
HEADERS = {'X-AP-Client-Id': 'ap', 'X-AP-API-Key': KEY}


def load_route():
    name = 'app.api.routes.ap_learning_results'
    assert util.find_spec(name), 'Missing AP results integration'
    return import_module(name)


def test_feature_exists():
    load_route()


@pytest.fixture
def api(monkeypatch):
    route = load_route()
    cfg = {'ap': {'key_sha256': hashlib.sha256(KEY.encode()).hexdigest(),
                  'scopes': [{'branch': 'poly', 'campuses': ['HN']}, {'branch': 'ptcd', 'campuses': ['DN']}]}}
    monkeypatch.setattr(settings, 'ap_analytics_clients_json', SecretStr(json.dumps(cfg)))
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    for model in (AcademicTerm, AcademicBlock, AcademicSubject, AcademicClass, AcademicStudent,
                  AcademicClassStudent, AcademicCourseMapping, AcademicClassCourseMapping, Snapshot):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            AcademicTerm(id='term', ap_term_id='ap-term', term_code='FA26', term_name='Fall', branch='poly'),
            AcademicSubject(id='subject', subject_code='WEB3023', subject_name='Web', branch='poly'),
            AcademicClass(id='class', ap_class_id='ap-class', term_id='term', subject_id='subject',
                          class_code='WEB1', class_name='Web1', campus='HN', branch='poly'),
            AcademicClassCourseMapping(class_id='class', openedx_course_id=COURSE)])
        for i in range(4):
            db.add(AcademicStudent(id=f's{i}', username=f'user{i}', student_code=f'PH00{i}', full_name=f'Name{i}'))
            db.add(AcademicClassStudent(class_id='class', student_id=f's{i}'))
        db.add_all([
            Snapshot(class_id='class', course_id=COURSE, username='user0', classification='NORMAL',
                     confidence_score=0., data_quality='GOOD', evidence_json={'scoring_version': SCORING_VERSION}),
            Snapshot(class_id='class', course_id=COURSE, username='user1', classification='POSSIBLE_IDLE',
                     calculated_at=datetime.utcnow() - timedelta(days=365), evidence_json={'answer_json': 'secret', 'scoring_version': SCORING_VERSION}),
            Snapshot(class_id='other', course_id=COURSE, username='user2', classification='NORMAL'),
            Snapshot(class_id='class', course_id='other-course', username='user3', classification='NORMAL'),
            Snapshot(class_id='class', course_id=COURSE, username='outsider', classification='NORMAL')])
        db.commit()
        app = FastAPI()
        app.include_router(route.router, prefix='/api/integrations/ap/v1')
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db, engine
    engine.dispose()


@pytest.mark.parametrize('headers', [{}, {'X-User-Role': 'admin'},
    {**HEADERS, 'X-AP-API-Key': 'wrong'}])
def test_credentials_required(api, headers):
    assert api[0].get(BASE + '/learning-results', params=PARAMS, headers=headers).status_code == 401


@pytest.mark.parametrize('config', ['', 'invalid', '{}', '{"ap":{"key_sha256":"bad","scopes":[]}}'])
def test_bad_config_fails_closed(api, monkeypatch, config):
    monkeypatch.setattr(settings, 'ap_analytics_clients_json', SecretStr(config))
    r = api[0].get(BASE + '/learning-results', params=PARAMS, headers=HEADERS)
    assert r.status_code == 503 and KEY not in r.text


@pytest.mark.parametrize('scope', [{'branch': 'poly', 'campus': 'DN'}, {'branch': 'ptcd', 'campus': 'HN'}])
def test_scope_pairs(api, scope):
    assert api[0].get(BASE + '/learning-results', params={**PARAMS, **scope}, headers=HEADERS).status_code == 403


def test_pagination_summary_missing_stale_and_privacy(api):
    client, _, engine = api
    statements = []
    def observe(conn, cursor, statement, params, context, many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', observe)
    r = client.get(BASE + '/learning-results', params={**PARAMS, 'limit': 2}, headers=HEADERS)
    event.remove(engine, 'before_cursor_execute', observe)
    assert r.status_code == 200, r.text
    data = r.json()
    assert r.headers['cache-control'] == 'no-store'
    assert data['total'] == 4 and data['next_offset'] == 2
    assert [x['student_code'] for x in data['items']] == ['PH000', 'PH001']
    assert data['summary']['snapshot_count'] == 2
    assert data['summary']['missing_snapshot_count'] == 2
    assert data['summary']['stale_snapshot_count'] == 1
    assert data['items'][0]['confidence_score'] == 0
    assert data['items'][1]['status'] == 'stale' and data['items'][1]['classification'] == 'POSSIBLE_IDLE'
    page = client.get(BASE + '/learning-results', params={**PARAMS, 'limit': 2, 'offset': 2}, headers=HEADERS).json()
    assert page['next_offset'] is None and page['summary'] == data['summary']
    assert all(x['status'] == 'missing' and x['confidence_score'] is None for x in page['items'])
    assert not any('analytics_tracking_events' in sql or sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in statements)
    assert len(statements) <= 10
    assert not any(field in json.dumps(data) for field in ['answer_json', 'evidence_json', 'permission_scope', 'outsider', 'email'])
    assert any('LIMIT' in sql and 'academic_students' in sql for sql in statements)


def test_exact_student_code_and_membership(api):
    client, _, _ = api
    url = BASE + '/students/{}/learning-results'
    assert client.get(url.format('PH000'), params=PARAMS, headers=HEADERS).json()['result']['student_code'] == 'PH000'
    for code in ('ph000', 'outsider'):
        assert client.get(url.format(code), params=PARAMS, headers=HEADERS).status_code == 404


def test_exact_class_context_and_input_bounds(api):
    client, _, _ = api
    for patch in ({'ap_term_id': 'term'}, {'subject_code': 'OTHER'}):
        assert client.get(BASE + '/learning-results', params={**PARAMS, **patch}, headers=HEADERS).status_code == 404
    assert client.get(BASE + '/learning-results', params={}, headers=HEADERS).status_code == 422
    for limit in (0, 201):
        assert client.get(BASE + '/learning-results', params={**PARAMS, 'limit': limit}, headers=HEADERS).status_code == 422


def test_ambiguous_class_and_block_disambiguation(api):
    client, db, _ = api
    db.add(AcademicBlock(id='block', term_id='term', ap_block_id='ap-block', block_code='B2', block_name='B2'))
    db.add(AcademicClass(id='class2', ap_class_id='ap-class', term_id='term', subject_id='subject',
                         block_id='block', class_code='WEB2', campus='HN', branch='poly'))
    db.commit()
    assert client.get(BASE + '/learning-results', params=PARAMS, headers=HEADERS).status_code == 409
    r = client.get(BASE + '/learning-results', params={**PARAMS, 'ap_block_id': 'ap-block'}, headers=HEADERS)
    assert r.status_code == 409 and r.json()['detail'] == 'COURSE_MAPPING_MISSING'


def test_inactive_roster_and_course_change(api):
    client, db, _ = api
    db.get(AcademicStudent, 's0').active = False
    db.query(AcademicClassCourseMapping).first().openedx_course_id = 'course-v1:FPL+WEB3023+SU26'
    db.commit()
    data = client.get(BASE + '/learning-results', params=PARAMS, headers=HEADERS).json()
    assert data['total'] == 3 and data['summary']['snapshot_count'] == 0
    assert all(x['status'] == 'missing' for x in data['items'])


def test_duplicate_normalized_snapshots_fail_closed(api):
    client, db, _ = api
    db.add(Snapshot(class_id='class', course_id=COURSE, username='USER0'))
    db.commit()
    assert client.get(BASE + '/learning-results', params=PARAMS, headers=HEADERS).status_code == 409


def test_get_only_and_security_documented(api):
    paths = api[0].get('/openapi.json').json()['paths']
    assert len(paths) == 2
    for path in paths.values():
        assert set(path) == {'get'} and path['get']['security']
    assert api[0].post(BASE + '/learning-results', params=PARAMS, headers=HEADERS).status_code == 405


def test_normalized_roster_collision_never_attributes_another_students_result(api):
    client, db, _ = api
    db.add(AcademicStudent(id='collision', username=' USER0 ', student_code='DIFFERENT_STUDENT'))
    db.add(AcademicClassStudent(class_id='class', student_id='collision'))
    db.commit()
    for path in ('/learning-results', '/students/DIFFERENT_STUDENT/learning-results', '/students/PH000/learning-results'):
        assert client.get(BASE + path, params=PARAMS, headers=HEADERS).status_code == 409


def test_blank_configured_client_id_is_rejected(api, monkeypatch):
    cfg = {'': {'key_sha256': hashlib.sha256(KEY.encode()).hexdigest(),
                'scopes': [{'branch': 'poly', 'campuses': ['HN']}]}}
    monkeypatch.setattr(settings, 'ap_analytics_clients_json', SecretStr(json.dumps(cfg)))
    assert api[0].get(BASE + '/learning-results', params=PARAMS,
                      headers={'X-AP-API-Key': KEY}).status_code == 503


@pytest.mark.parametrize('patch,expected', [({'ap_term_id': 'bad'}, 404), ({'limit': 201}, 422), ({'campus': 'DN'}, 403)])
def test_error_responses_cannot_be_cached(api, patch, expected):
    r = api[0].get(BASE + '/learning-results', params={**PARAMS, **patch}, headers=HEADERS)
    assert r.status_code == expected and r.headers.get('cache-control') == 'no-store'


def test_duplicate_student_codes_are_ambiguous(api):
    client, db, _ = api
    db.get(AcademicStudent, 's1').student_code = 'PH000'
    db.commit()
    assert client.get(BASE + '/students/PH000/learning-results', params=PARAMS, headers=HEADERS).status_code == 409


def test_openapi_does_not_claim_client_id_is_an_alternative_to_the_key(api):
    spec = api[0].get('/openapi.json').json()
    operation = spec['paths']['/api/integrations/ap/v1/classes/{ap_class_id}/learning-results']['get']
    assert operation['security'] == [{'APAPIKey': []}]
    assert not any(p['name'] == 'X-AP-Client-Id' for p in operation['parameters'])


def test_shared_key_alone_authenticates_without_client_id(api):
    r = api[0].get(BASE + '/learning-results', params=PARAMS, headers={'X-AP-API-Key': KEY})
    assert r.status_code == 200


def test_shared_key_configuration_is_available():
    from app.core.config import Settings
    assert 'ap_analytics_config_json' in Settings.model_fields


@pytest.mark.parametrize('branch,campus', [('poly', 'HN'), ('ptcd', 'DN')])
def test_one_shared_key_covers_both_explicit_scopes(api, monkeypatch, branch, campus):
    from app.core.ap_analytics_auth import get_ap_analytics_client
    config = {'key_sha256': hashlib.sha256(KEY.encode()).hexdigest(),
              'scopes': [{'branch': 'poly', 'campuses': ['HN']}, {'branch': 'ptcd', 'campuses': ['DN']}]}
    monkeypatch.setattr(settings, 'ap_analytics_config_json', SecretStr(json.dumps(config)))
    # Same API credential grants only the declared branch/campus pairs.
    client = get_ap_analytics_client(KEY)
    client.assert_scope(branch, campus)
    r = api[0].get(BASE + '/learning-results', params=PARAMS, headers={'X-AP-API-Key': KEY})
    assert r.status_code == 200


def test_bad_shared_config_never_falls_back_to_legacy_key(api, monkeypatch):
    monkeypatch.setattr(settings, 'ap_analytics_config_json', SecretStr('invalid'))
    assert api[0].get(BASE + '/learning-results', params=PARAMS, headers=HEADERS).status_code == 503


def test_multiple_legacy_keys_fail_closed(api, monkeypatch):
    one = {'key_sha256': hashlib.sha256(KEY.encode()).hexdigest(),
           'scopes': [{'branch': 'poly', 'campuses': ['HN']}]}
    monkeypatch.setattr(settings, 'ap_analytics_clients_json', SecretStr(json.dumps({'one': one, 'two': one})))
    assert api[0].get(BASE + '/learning-results', params=PARAMS, headers=HEADERS).status_code == 503


def test_client_id_header_does_not_choose_another_key(api):
    r = api[0].get(BASE + '/learning-results', params=PARAMS,
                  headers={**HEADERS, 'X-AP-Client-Id': 'ignored-legacy-header'})
    assert r.status_code == 200



def test_old_scoring_rules_are_stale_in_rows_and_whole_class_summary(api):
    client, db, _ = api
    snapshot = db.query(Snapshot).filter(Snapshot.class_id == 'class', Snapshot.username == 'user0').one()
    snapshot.evidence_json = {'scoring_version': 'learning_behavior_audit_v2', 'answer_json': 'private'}
    db.commit()
    result = client.get(BASE + '/learning-results', params=PARAMS, headers={'X-AP-API-Key': KEY})
    assert result.status_code == 200
    data = result.json()
    assert data['summary']['stale_snapshot_count'] == 2
    assert data['items'][0]['status'] == 'stale'
    assert data['items'][0]['snapshot_recompute_required'] is True
    assert data['items'][0]['classification'] == 'NORMAL'  # historical result, no reclassification on GET
    assert 'BEHAVIOR_RULES_UPDATED' in data['items'][0]['reason_codes']
    assert not any(value in result.text for value in ['answer_json', 'scoring_version', 'private'])
