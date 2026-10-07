from copy import deepcopy
from types import SimpleNamespace
import json

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import question_bank_v2 as routes
from app.core.rbac import UserContext
from app.models.question_bank import CourseQuizInstance
from app.schemas import question_bank as schemas
from app.tests.test_legacy_quiz_cms_old_import import _session

COURSE = 'course-v1:FPL+SUB+FA26'
UNIT = 'block-v1:FPL+SUB+FA26+type@vertical+block@quiz-unit'


def instance(db, **changes):
    fields = dict(id='quiz', openedx_course_id=COURSE, openedx_unit_node_id=UNIT,
                  openedx_quiz_node_id='quiz-root', subject_id='subject', chapter_id='chapter',
                  bank_release_id='release', status='created', metadata_json={
                      'quiz_title': 'Quiz 1', 'question_ids': ['q1'],
                      'timer_config': {'custom_timer_enabled': True, 'duration_seconds': 900,
                                       'time_limit_minutes': 15, 'cooldown_seconds': 300,
                                       'lock_after_timeout': True, 'native_timed_exam': False}})
    fields.update(changes)
    row = CourseQuizInstance(**fields)
    db.add(row)
    db.commit()
    return row


class TimerConnector:
    def __init__(self, *, fail=False, duration=1800):
        self.calls = []
        self.fail, self.duration = fail, duration

    async def update_quiz_timer_duration(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('LMS unavailable')
        return {'success': True, 'previous_duration_seconds': 900,
                'config': {'course_id': COURSE, 'unit_usage_key': UNIT,
                           'duration_seconds': self.duration}}


def arrange(monkeypatch, connector):
    from app.modules.openedx_connector import factory
    monkeypatch.setattr(factory, 'get_openedx_connector', lambda: connector)
    monkeypatch.setattr(routes, '_require_release', lambda *_args: None)
    return UserContext(user_id='admin', role='admin', permissions={'publish_questions'})


@pytest.mark.asyncio
async def test_edit_duration_preserves_quiz_identity_and_other_configuration(monkeypatch):
    connector = TimerConnector()
    user = arrange(monkeypatch, connector)
    with _session() as db:
        row = instance(db)
        previous = deepcopy(row.metadata_json)
        await routes.update_course_quiz_duration(
            'quiz', SimpleNamespace(time_limit_minutes=30), db=db, user=user)
        db.refresh(row)
        assert row.openedx_unit_node_id == UNIT
        assert row.openedx_quiz_node_id == 'quiz-root'
        assert row.status == 'created'
        assert row.metadata_json['question_ids'] == previous['question_ids']
        timer = row.metadata_json['timer_config']
        assert timer['duration_seconds'] == 1800
        assert timer['time_limit_minutes'] == 30
        for key in ('cooldown_seconds', 'lock_after_timeout', 'native_timed_exam', 'custom_timer_enabled'):
            assert timer[key] == previous['timer_config'][key]
        assert db.query(CourseQuizInstance).count() == 1
        assert connector.calls == [{'course_id': COURSE, 'unit_usage_key': UNIT,
                                    'duration_seconds': 1800, 'actor': 'admin'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['planned', 'creating', 'rolled_back', 'rollback_manual_required'])
async def test_unfinished_or_removed_quiz_cannot_edit_duration(monkeypatch, status):
    connector = TimerConnector()
    user = arrange(monkeypatch, connector)
    with _session() as db:
        instance(db, status=status)
        with pytest.raises(HTTPException) as exc:
            await routes.update_course_quiz_duration('quiz', SimpleNamespace(time_limit_minutes=30), db=db, user=user)
        assert exc.value.status_code == 409
        assert not connector.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('fail,duration', [(True, 1800), (False, 900)])
async def test_failed_or_unconfirmed_lms_update_keeps_local_duration(monkeypatch, fail, duration):
    connector = TimerConnector(fail=fail, duration=duration)
    user = arrange(monkeypatch, connector)
    with _session() as db:
        row = instance(db)
        previous = deepcopy(row.metadata_json)
        with pytest.raises(HTTPException) as exc:
            await routes.update_course_quiz_duration('quiz', SimpleNamespace(time_limit_minutes=30), db=db, user=user)
        assert exc.value.status_code == 502
        db.refresh(row)
        assert row.metadata_json == previous


@pytest.mark.asyncio
async def test_duration_edit_checks_release_scope_before_calling_lms(monkeypatch):
    connector = TimerConnector()
    user = arrange(monkeypatch, connector)
    def deny(*_args):
        raise HTTPException(403, 'Forbidden')
    monkeypatch.setattr(routes, '_require_release', deny)
    with _session() as db:
        instance(db)
        with pytest.raises(HTTPException) as exc:
            await routes.update_course_quiz_duration('quiz', SimpleNamespace(time_limit_minutes=30), db=db, user=user)
        assert exc.value.status_code == 403
        assert not connector.calls


@pytest.mark.parametrize('value', [None, 0, 301, 1.5, True])
def test_duration_request_rejects_invalid_minutes(value):
    with pytest.raises(ValidationError):
        schemas.CourseQuizDurationUpdateRequest(time_limit_minutes=value)


@pytest.mark.asyncio
async def test_real_connector_sends_duration_only_to_lms(monkeypatch):
    from app.modules.openedx_connector import real
    connector = real.RealOpenEdXConnector()
    connector.lms_base_url = 'https://lms.example'
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'success': True, 'config': {'duration_seconds': 1800}})
    client_class = httpx.AsyncClient
    monkeypatch.setattr(real.httpx, 'AsyncClient',
                        lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs))
    await connector.update_quiz_timer_duration(course_id=COURSE, unit_usage_key=UNIT,
                                               duration_seconds=1800, actor='admin')
    assert len(requests) == 1
    assert str(requests[0].url) == 'https://lms.example/api/unit-reset/v1/quiz-config/duration'
    assert json.loads(requests[0].content) == {
        'course_id': COURSE, 'unit_usage_key': UNIT, 'duration_seconds': 1800, 'actor': 'admin'}
