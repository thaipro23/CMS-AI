from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.services import ap_academic_sync
from app.services.ap_academic_sync import APAcademicClient


class FakeResponse:
    def __init__(self, payload: Any):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeHttpClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({'method': 'GET', 'url': url, **kwargs})
        if url.endswith('/get-campus'):
            return FakeResponse({'status': 'success', 'data': [
                {'campus_code': 'HN', 'campus_name': 'Hà Nội'},
                {'code': 'HCM', 'name': 'Hồ Chí Minh'},
            ]})
        if url.endswith('/get-all-subject'):
            return FakeResponse({'code': 200, 'data': {'items': [
                {'subject_code': 'AUT218', 'subject_name': 'Hệ thống điều khiển thông minh'},
                {'subjectCode': 'MEC229', 'subjectName': 'Đồ gá'},
            ]}})
        raise AssertionError(f'unexpected GET {url}')

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({'method': 'POST', 'url': url, **kwargs})
        if url.endswith('/get-data-cms'):
            return FakeResponse({'status': 'success', 'data': {'class': [], 'student': []}})
        raise AssertionError(f'unexpected POST {url}')


@pytest.fixture(autouse=True)
def internal_api_contract(monkeypatch: pytest.MonkeyPatch):
    FakeHttpClient.calls = []
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', FakeHttpClient)
    monkeypatch.setattr(settings, 'academic_ap_get_course_file_cache_enabled', False)
    monkeypatch.setattr(settings, 'academic_ap_tls_mode', 'strict')


def make_client() -> APAcademicClient:
    # Deliberately provide a stale key. Canonical internal requests must not leak it.
    return APAcademicClient(
        base_url='https://api.poly.edu.vn/api/cms',
        api_key='STALE_SECRET_MUST_NOT_BE_SENT',
    )


def assert_keyless(call: dict[str, Any]) -> None:
    headers = {str(k).lower(): str(v) for k, v in (call.get('headers') or {}).items()}
    assert 'authorization' not in headers
    assert 'x-api-key' not in headers
    assert 'api-key' not in headers
    assert 'campus' not in headers


def test_get_campus_uses_product_and_no_api_key():
    campuses = make_client().get_campuses(branch='ptcd')
    assert [item['campus_code'] for item in campuses] == ['hn', 'hcm']
    call = FakeHttpClient.calls[-1]
    assert call['method'] == 'GET'
    assert call['url'] == 'https://api.poly.edu.vn/api/cms/get-campus'
    assert call['params'] == {'product': 'PTCD'}
    assert_keyless(call)


def test_get_all_subject_is_product_term_scoped_keyless_catalog():
    subjects = make_client().get_subjects(branch='poly', term_name='Fall 2026')
    assert [item['subject_code'] for item in subjects] == ['AUT218', 'MEC229']
    call = FakeHttpClient.calls[-1]
    assert call['method'] == 'GET'
    assert call['url'] == 'https://api.poly.edu.vn/api/cms/get-all-subject'
    assert call['params'] == {'product': 'POLY', 'term_name': 'Fall 2026'}
    assert_keyless(call)


def test_get_data_cms_posts_existing_payload_without_api_key():
    payload = make_client().get_division(campus='hn', term_name='Fall 2026', subject_code='aut218')
    assert payload == {'class': [], 'student': []}
    call = FakeHttpClient.calls[-1]
    assert call['method'] == 'POST'
    assert call['url'] == 'https://api.poly.edu.vn/api/cms/get-data-cms'
    assert call['json'] == {'campus': 'hn', 'term_name': 'Fall 2026', 'subject_code': 'AUT218'}
    assert_keyless(call)


def test_strict_tls_has_no_old_host_bypass():
    client = make_client()
    assert client._verify_config('https://api.poly.edu.vn/api/cms/get-all-subject') is True
    assert client._verify_config('https://api_v2.poly.edu.vn/get-course') is True
