from __future__ import annotations

import json

from app.services import ap_academic_sync


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            'status': 1,
            'code': 200,
            'data': {
                'courses': [
                    {'code': 'ACC106', 'name': 'Quản trị tài chính'},
                    {'skill_code': 'WEB3023', 'subject_name': 'Thiết kế Web'},
                ]
            },
        }


class _FakeHttpClient:
    request_count = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None, params=None):
        type(self).request_count += 1
        return _FakeResponse()


def _prepare(monkeypatch, tmp_path):
    _FakeHttpClient.request_count = 0
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_endpoint', '/get-course')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_key', 'api-secret-123456')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_refresh', False)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_ttl_seconds', 86400)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_dir', str(tmp_path))
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', _FakeHttpClient)


def test_get_course_supports_nested_course_aliases_and_file_cache(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    client = ap_academic_sync.APAcademicClient()

    first = client.get_subjects(branch='poly', term_name='Summer 2026')
    second = client.get_subjects(branch='poly', term_name='Summer 2026')

    assert [item['subject_code'] for item in first] == ['ACC106', 'WEB3023']
    assert first[0]['subject_name'] == 'Quản trị tài chính'
    assert second[0]['_catalog_source'] == 'ap.get-course.file-cache'
    assert _FakeHttpClient.request_count == 1

    cache_files = list(tmp_path.glob('ap_get_course_subjects_*.json'))
    assert len(cache_files) == 1
    payload = json.loads(cache_files[0].read_text(encoding='utf-8'))
    assert payload['source'] == 'ap.get-course'
    assert payload['discovery_branch'] == 'poly'
    assert payload['term_name'] == 'Summer 2026'
