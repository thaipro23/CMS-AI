from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.services import ap_academic_sync
from app.services.ap_academic_sync import APAcademicClient
from app.services.academic.ap_importer import AcademicImportService


class FakeResponse:
    def __init__(self, payload: Any):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeHttpClient:
    calls: list[dict[str, Any]] = []
    division_payload: dict[str, Any] = {}

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
            return FakeResponse(self.division_payload)
        raise AssertionError(f'unexpected POST {url}')


@pytest.fixture(autouse=True)
def internal_api_contract(monkeypatch: pytest.MonkeyPatch):
    FakeHttpClient.calls = []
    FakeHttpClient.division_payload = {
        'status': 1,
        'code': 200,
        'message': 'success',
        'data': {
            'term': {
                'id': 68,
                'term_name': 'Fall 2026',
                'startday': '2026-08-31',
                'endday': '2026-12-27',
                'block': [
                    {
                        'id': 122,
                        'term_id': 68,
                        'block_name': 'Block 1',
                        'start_day': '2026-08-31',
                        'end_day': '2026-10-20',
                        'created_at': '2026-06-11T07:01:21.000000Z',
                        'created_by': None,
                        'updated_at': None,
                        'updated_by': None,
                    },
                    {
                        'id': 123,
                        'term_id': 68,
                        'block_name': 'Block 2',
                        'start_day': '2026-10-21',
                        'end_day': '2026-12-27',
                    },
                ],
            },
            'class': [
                {
                    'id': 56714,
                    'group_name': 'SA2101',
                    'psubject_name': 'Nhập môn lập trình',
                    'pterm_name': 'Fall 2026',
                    'teacher': 'luanpv10',
                    'psubject_code': 'COM108',
                    'skill_code': 'COM108',
                    'pterm_id': 68,
                    'block_id': 123,
                    'start_date': '2026-10-30',
                    'end_date': '2026-12-11',
                    'student': [
                        {
                            'name': 'Đào Việt Anh',
                            'email': 'abc@gmail.com',
                            'phone': '',
                            'username': 'anhdvth09108',
                            'user_code': 'TH09108',
                            'total_relearn': 0,
                        }
                    ],
                }
            ],
        },
    }
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


def test_get_data_cms_accepts_new_numeric_success_envelope_and_date_only_payload():
    payload = make_client().get_division(campus='hn', term_name='Fall 2026', subject_code='com108')
    assert payload['term']['id'] == 68
    assert payload['term']['startday'] == '2026-08-31'
    assert payload['term']['block'][1]['start_day'] == '2026-10-21'
    assert payload['class'][0]['group_name'] == 'SA2101'
    assert payload['class'][0]['teacher'] == 'luanpv10'
    assert payload['class'][0]['student'][0]['user_code'] == 'TH09108'
    call = FakeHttpClient.calls[-1]
    assert call['method'] == 'POST'
    assert call['url'] == 'https://api.poly.edu.vn/api/cms/get-data-cms'
    assert call['json'] == {'campus': 'hn', 'term_name': 'Fall 2026', 'subject_code': 'COM108'}
    assert_keyless(call)


def test_get_data_cms_keeps_legacy_string_success_and_iso_utc_payload_compatible():
    FakeHttpClient.division_payload = {
        'status': 'success',
        'data': {
            'term': {
                'id': 65,
                'term_name': 'Summer 2026',
                'startday': '2026-05-10T17:00:00.000Z',
                'endday': '2026-09-12T17:00:00.000Z',
                'block': [
                    {
                        'id': 132,
                        'term_id': 65,
                        'block_name': 'Block 1',
                        'start_day': '2026-05-10T17:00:00.000Z',
                        'end_day': '2026-06-27T17:00:00.000Z',
                    }
                ],
            },
            'class': [
                {
                    'id': 101328,
                    'group_name': 'AE21306',
                    'psubject_name': 'Năng lượng tái tạo',
                    'pterm_name': 'Summer 2026',
                    'teacher': 'hiepht7',
                    'psubject_code': 'AUT2131',
                    'skill_code': 'AUT213',
                    'pterm_id': 65,
                    'block_id': 132,
                    'start_date': '2026-05-10T17:00:00.000Z',
                    'end_date': '2026-06-18T17:00:00.000Z',
                    'student': [
                        {
                            'name': 'Nguyễn Tiến Anh',
                            'email': 'abc@gmail.com',
                            'phone': '',
                            'username': 'anhntph68259',
                            'user_code': 'PH68259',
                            'total_relearn': 0,
                        }
                    ],
                }
            ],
        },
    }
    payload = make_client().get_division(campus='hn', term_name='Summer 2026', subject_code='AUT2131')
    assert payload['term']['id'] == 65
    assert payload['term']['startday'].endswith('Z')
    assert payload['class'][0]['psubject_code'] == 'AUT2131'
    assert payload['class'][0]['skill_code'] == 'AUT213'
    assert payload['class'][0]['student'][0]['total_relearn'] == 0


def test_manual_import_normalizes_both_get_data_cms_envelopes():
    new_envelope = FakeHttpClient.division_payload
    new_root = AcademicImportService._normalize_payload(new_envelope)
    assert new_root['term']['term_name'] == 'Fall 2026'
    assert new_root['class'][0]['psubject_code'] == 'COM108'

    old_envelope = {
        'status': 'success',
        'data': {
            'term': {'id': 65, 'term_name': 'Summer 2026'},
            'class': [],
        },
    }
    old_root = AcademicImportService._normalize_payload(old_envelope)
    assert old_root['term']['term_name'] == 'Summer 2026'
    assert old_root['class'] == []


def test_manual_import_rejects_failed_envelope_before_mutating_data():
    with pytest.raises(ValueError, match='trạng thái lỗi'):
        AcademicImportService._normalize_payload({
            'status': 0,
            'code': 500,
            'message': 'upstream failed',
            'data': {'term': {}, 'class': []},
        })


def test_strict_tls_has_no_old_host_bypass():
    client = make_client()
    assert client._verify_config('https://api.poly.edu.vn/api/cms/get-all-subject') is True
    assert client._verify_config('https://api_v2.poly.edu.vn/get-course') is True
