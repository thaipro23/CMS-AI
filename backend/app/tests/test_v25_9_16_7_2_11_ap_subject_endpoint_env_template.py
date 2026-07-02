from __future__ import annotations

from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    requests: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None, params=None):
        self.__class__.requests.append({'url': url, 'headers': headers or {}, 'params': params or {}})
        return _FakeResponse({
            'status': 1,
            'code': 200,
            'message': 200,
            'data': [
                {'subject_code': 'ACC106', 'skill_code': 'ACC106', 'subject_name': 'Quản trị tài chính'},
            ],
        })


def _prepare(monkeypatch, tmp_path, endpoint='/api/cms/get-subject-cms?campus_code=ph&term_name='):
    _FakeHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_api_base_url', 'https://apitest.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_get_subject_endpoint', endpoint)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_key', None)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_subject_cms_file_cache_enabled', False)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_subject_cms_file_cache_dir', str(tmp_path))
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_enabled', None)
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', _FakeHttpClient)


def test_subject_cms_default_env_template_keeps_static_ph_and_fills_term(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    client = ap_academic_sync.APAcademicClient()

    subjects = client.get_subjects(branch='poly', term_name='Summer 2026', campus='ps')

    assert subjects[0]['subject_code'] == 'ACC106'
    request = _FakeHttpClient.requests[0]
    assert request['url'] == 'https://apitest.poly.edu.vn/api/cms/get-subject-cms?campus_code=ph&term_name=Summer+2026'
    assert request['params'] == {}
    assert 'campus' not in request['headers']


def test_subject_cms_future_env_template_can_remove_campus_code(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, endpoint='/api/cms/get-subject-cms?term_name=')
    client = ap_academic_sync.APAcademicClient()

    client.get_subjects(branch='poly', term_name='Summer 2026', campus='ph')

    request = _FakeHttpClient.requests[0]
    assert request['url'] == 'https://apitest.poly.edu.vn/api/cms/get-subject-cms?term_name=Summer+2026'
    assert 'campus_code' not in request['url']


def test_subject_cache_key_changes_when_endpoint_template_changes(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, endpoint='/api/cms/get-subject-cms?campus_code=ph&term_name=')
    client = ap_academic_sync.APAcademicClient()
    first = client._subject_cache_file(branch='poly', term_name='Summer 2026')

    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_get_subject_endpoint', '/api/cms/get-subject-cms?term_name=')
    second = client._subject_cache_file(branch='poly', term_name='Summer 2026')

    assert first != second
