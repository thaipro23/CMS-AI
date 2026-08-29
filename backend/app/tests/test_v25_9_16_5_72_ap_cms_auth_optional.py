from __future__ import annotations

import pytest

from app.services import ap_academic_sync


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {'status': 1, 'code': 200, 'data': [{'subject_code': 'WEB3023', 'subject_name': 'Thiết kế Web'}]}


class _FakeHttpClient:
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.__class__.requests.append({'url': url, 'headers': headers or {}, 'params': params or {}})
        return _FakeResponse()


def _prepare(monkeypatch, *, api_key=None):
    _FakeHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_endpoint', '/get-course')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_key', api_key)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_enabled', False)
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', _FakeHttpClient)


def test_get_course_catalog_requires_api_key_before_http_call(monkeypatch):
    _prepare(monkeypatch)

    with pytest.raises(RuntimeError, match='ACADEMIC_AP_API_KEY'):
        ap_academic_sync.APAcademicClient().get_subjects(
            branch='poly', term_name='Summer 2026', campus='ph'
        )

    assert _FakeHttpClient.requests == []


def test_get_course_catalog_sends_bearer_api_key(monkeypatch):
    _prepare(monkeypatch, api_key='api-secret-123456')
    subjects = ap_academic_sync.APAcademicClient().get_subjects(
        branch='poly', term_name='Summer 2026', campus='ph'
    )

    assert subjects[0]['subject_code'] == 'WEB3023'
    assert _FakeHttpClient.requests[0]['params'] == {'branch': 'poly', 'term_name': 'Summer 2026'}
    assert _FakeHttpClient.requests[0]['headers']['Authorization'] == 'Bearer api-secret-123456'


def test_get_data_cms_still_requires_api_key(monkeypatch):
    _prepare(monkeypatch)

    with pytest.raises(RuntimeError, match='ACADEMIC_AP_API_KEY'):
        ap_academic_sync.APAcademicClient().get_division(
            campus='ph', term_name='Summer 2026', subject_code='WEB3023'
        )
