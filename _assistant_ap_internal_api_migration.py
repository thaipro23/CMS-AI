from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, new_block: str, label: str) -> str:
    start_idx = text.find(start)
    if start_idx < 0:
        raise RuntimeError(f'{label}: start marker not found')
    end_idx = text.find(end, start_idx)
    if end_idx < 0:
        raise RuntimeError(f'{label}: end marker not found')
    return text[:start_idx] + new_block + text[end_idx:]


# ---------------------------------------------------------------------------
# 1) Runtime config: canonical keyless internal CMS API.
# ---------------------------------------------------------------------------
config_path = Path('backend/app/core/config.py')
config = config_path.read_text()
old_config = """    academic_ap_sync_enabled: bool = True
    academic_ap_api_base_url: str = 'https://api_v2.poly.edu.vn'
    # Subject catalog source of truth. Discovery always calls this endpoint with
    # branch=poly and the selected term_name. The requested UI branch is retained
    # as metadata only because AP's ptcd catalog has historically been noisy.
    academic_ap_get_course_endpoint: str = '/get-course'
    academic_ap_api_key: str | None = None
    academic_ap_request_timeout_seconds: int = 60
    # TLS verification mode for AP integrations other than api_v2.poly.edu.vn.
    # api_v2.poly.edu.vn is an approved host-specific exception and always uses
    # verify=False because its served certificate currently mismatches the hostname.
    # strict: verify CA chain + hostname (default for every other host).
    # chain_only: verify CA chain but skip hostname check.
    # off: disable all certificate verification. Use only for an explicitly approved
    # internal endpoint with separate network controls.
    academic_ap_tls_mode: str = 'strict'
"""
new_config = """    academic_ap_sync_enabled: bool = True
    # Polytechnic internal CMS API. These endpoints are trusted internal services
    # and intentionally do not use API keys/Bearer tokens.
    academic_ap_api_base_url: str = 'https://api.poly.edu.vn/api/cms'
    academic_ap_get_all_subject_endpoint: str = '/get-all-subject'
    academic_ap_get_campus_endpoint: str = '/get-campus'
    academic_ap_get_data_cms_endpoint: str = '/get-data-cms'
    # Deprecated rolling-upgrade aliases. The canonical client does not use the
    # old /get-course endpoint or send this key to the internal CMS API.
    academic_ap_get_course_endpoint: str = '/get-all-subject'
    academic_ap_api_key: str | None = None
    academic_ap_request_timeout_seconds: int = 60
    # New api.poly.edu.vn integration uses normal TLS verification by default.
    # chain_only/off remain emergency deployment knobs, not host-specific bypasses.
    academic_ap_tls_mode: str = 'strict'
"""
config = replace_once(config, old_config, new_config, 'config AP settings')
config = replace_once(
    config,
    """        if not settings.academic_ap_api_key or settings.academic_ap_api_key.startswith('CHANGE_ME') or len(settings.academic_ap_api_key) < 12:\n            errors.append('ACADEMIC_AP_API_KEY is required when ACADEMIC_AP_SYNC_ENABLED=true')\n""",
    "",
    'production AP key requirement',
)
config_path.write_text(config)


# ---------------------------------------------------------------------------
# 2) AP client: new endpoints, no API key, strict TLS, robust response shapes.
# ---------------------------------------------------------------------------
client_path = Path('backend/app/services/ap_academic_sync.py')
client = client_path.read_text()
client = client.replace(
    "# v25.9.16.2.1: AP credentials are read from environment settings.\n# Never hardcode or log the AP API key.\n",
    "# Polytechnic internal CMS API integration. The canonical endpoints are keyless;\n# never attach unrelated Authorization credentials to these requests.\n",
)
verify_block = """    def _verify_config(self, endpoint: str | None = None) -> bool | ssl.SSLContext:
        \"\"\"Return httpx TLS verification for the internal CMS API.

        ``api.poly.edu.vn`` uses the normal HTTPS trust chain. There is no
        hostname-specific verification bypass. Deployment operators may still use
        the generic chain_only/off modes temporarily, but strict is the default.
        \"\"\"
        mode = self.tls_mode
        if mode in {'off', 'false', '0', 'no', 'disabled'}:
            return False
        if mode in {'chain_only', 'chain-only', 'chainonly'}:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            return ctx
        return True

"""
client = replace_block(client, '    def _verify_config(', '    def _headers(', verify_block, 'TLS helper')
headers_block = """    def _headers(self) -> dict[str, str]:
        # api.poly.edu.vn/api/cms is an internal keyless API. Keep headers minimal
        # so a stale ACADEMIC_AP_API_KEY can never leak to these endpoints.
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

"""
client = replace_block(client, '    def _headers(', '    def _api_endpoint(', headers_block, 'keyless headers')
client = client.replace(
    "for key in ('data', 'items', 'subjects', 'course', 'courses'):",
    "for key in ('data', 'items', 'subjects', 'course', 'courses', 'result', 'results', 'list'):",
)
client = client.replace("'/tmp/ai-server-ap-cache/get-course'", "'/tmp/ai-server-ap-cache/get-all-subject'")
client = client.replace("academic_ap_get_course_endpoint', '/get-course'", "academic_ap_get_all_subject_endpoint', '/get-all-subject'")
client = client.replace('ap_get_course_subjects_', 'ap_get_all_subjects_')
client = client.replace('ap.get-course.file-cache', 'ap.get-all-subject.file-cache')
client = client.replace("'source': 'ap.get-course'", "'source': 'ap.get-all-subject'")
client = client.replace("'discovery_branch': 'poly'", "'discovery_branch': _lower(branch) or 'poly'")

normalize_subject_block = """    def _normalize_subject_items(self, items: Any, *, requested_branch: str, campus: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise RuntimeError('AP get-all-subject trả dữ liệu môn không đúng định dạng list.')
        requested = _lower(requested_branch) or 'poly'
        expected_product = 'POLY' if requested == 'poly' else 'PTCD'
        subjects: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            item_product = _clean(
                item.get('product') or item.get('branch') or item.get('system') or item.get('product_code')
            ).upper()
            if item_product and item_product not in {expected_product, requested.upper()}:
                continue
            code = _clean(
                item.get('psubject_code')
                or item.get('subject_code')
                or item.get('subjectCode')
                or item.get('course_code')
                or item.get('courseCode')
                or item.get('code')
                or item.get('skill_code')
                or item.get('id')
            ).upper()
            if not code or code in seen:
                continue
            seen.add(code)
            normalized = dict(item)
            normalized['subject_code'] = code
            normalized.setdefault('psubject_code', code)
            normalized['discovery_branch'] = requested
            normalized['requested_branch'] = requested
            subject_name = _clean(
                item.get('psubject_name')
                or item.get('subject_name')
                or item.get('subjectName')
                or item.get('course_name')
                or item.get('courseName')
                or item.get('name')
                or item.get('label')
            )
            if subject_name:
                normalized.setdefault('subject_name', subject_name)
                normalized.setdefault('psubject_name', subject_name)
            if campus:
                normalized.setdefault('campus_code', _lower(campus))
            subjects.append(normalized)
        return subjects

    @staticmethod
    def _normalize_campus_items(items: Any, *, branch: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise RuntimeError('AP get-campus trả dữ liệu cơ sở không đúng định dạng list.')
        requested = _lower(branch) or 'poly'
        product = 'POLY' if requested == 'poly' else 'PTCD'
        campuses: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if isinstance(item, dict):
                raw_code = _clean(
                    item.get('campus_code')
                    or item.get('campusCode')
                    or item.get('code')
                    or item.get('value')
                    or item.get('campus')
                    or item.get('id')
                    or item.get('name')
                )
                label = _clean(
                    item.get('campus_name')
                    or item.get('campusName')
                    or item.get('name')
                    or item.get('label')
                    or raw_code
                )
            else:
                raw_code = _clean(item)
                label = raw_code
            code = _lower(raw_code)
            if not code or code in seen:
                continue
            seen.add(code)
            campuses.append({
                'campus_code': code,
                'campus_name': label or raw_code,
                'product': product,
                'branch': requested,
                'api_value': raw_code,
            })
        return campuses

"""
client = replace_block(client, '    def _normalize_subject_items(', '    def _read_subject_cache(', normalize_subject_block, 'subject/campus normalizers')

get_subjects_block = """    def get_campuses(self, *, branch: str = 'poly') -> list[dict[str, Any]]:
        normalized_branch = _lower(branch) or 'poly'
        if normalized_branch not in {'poly', 'ptcd'}:
            raise ValueError('Hệ AP chỉ hỗ trợ poly hoặc ptcd.')
        product = 'POLY' if normalized_branch == 'poly' else 'PTCD'
        endpoint = self._api_endpoint(
            getattr(settings, 'academic_ap_get_campus_endpoint', '/get-campus'),
            '/get-campus',
        )
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config(endpoint)) as http:
            response = http.get(endpoint, headers=self._headers(), params={'product': product})
            response.raise_for_status()
            data = response.json()
        self._ensure_success_response(data, label='AP get-campus')
        root = data.get('data') if isinstance(data, dict) and isinstance(data.get('data'), (dict, list)) else data
        if isinstance(root, dict):
            for key in ('data', 'items', 'campuses', 'campus', 'result', 'results', 'list'):
                if isinstance(root.get(key), list):
                    root = root[key]
                    break
        campuses = self._normalize_campus_items(root, branch=normalized_branch)
        if not campuses:
            raise RuntimeError(f'AP get-campus không trả cơ sở nào cho product={product}.')
        return campuses

    def get_subjects(self, *, branch: str, term_name: str | None = None, campus: str | None = None) -> list[dict[str, Any]]:
        normalized_branch = _lower(branch) or 'poly'
        if normalized_branch not in {'poly', 'ptcd'}:
            raise ValueError('Hệ AP chỉ hỗ trợ poly hoặc ptcd.')
        normalized_term = _clean(term_name)
        cached = self._read_subject_cache(branch=normalized_branch, term_name=normalized_term or None, campus=None)
        if cached:
            return cached

        endpoint = self._api_endpoint(
            getattr(settings, 'academic_ap_get_all_subject_endpoint', '/get-all-subject'),
            '/get-all-subject',
        )
        # get-all-subject is intentionally global/keyless. Do not send the legacy
        # branch/term query parameters; scope is applied locally when fields exist.
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config(endpoint)) as http:
            response = http.get(endpoint, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        items = self._extract_list_response(data, label='AP get-all-subject')
        subjects = self._normalize_subject_items(items, requested_branch=normalized_branch, campus=None)
        if normalized_term:
            scoped: list[dict[str, Any]] = []
            for item in subjects:
                item_term = _clean(
                    item.get('term_name') or item.get('termName') or item.get('semester') or item.get('semester_name')
                )
                if not item_term or item_term.casefold() == normalized_term.casefold():
                    scoped.append(item)
            subjects = scoped
        if not subjects:
            scope = f'term_name={normalized_term}' if normalized_term else 'global catalog'
            raise RuntimeError(f'AP get-all-subject không trả môn nào cho {scope}, requested_branch={normalized_branch}.')
        for item in subjects:
            item['_catalog_source'] = 'ap.get-all-subject'
            item['_catalog_scope'] = 'term' if normalized_term else 'global'
            item['_catalog_term_name'] = normalized_term or None
        self._write_subject_cache(
            branch=normalized_branch,
            term_name=normalized_term or None,
            campus=None,
            subjects=subjects,
        )
        return subjects

"""
client = replace_block(client, '    def get_subjects(', '    def get_division(', get_subjects_block, 'new campus/subject API methods')

division_block = """    def get_division(self, *, campus: str, term_name: str, subject_code: str) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError('Thiếu ACADEMIC_AP_API_BASE_URL khi gọi /get-data-cms.')
        body = {
            'campus': _clean(campus),
            'term_name': _clean(term_name),
            'subject_code': _clean(subject_code).upper(),
        }
        endpoint = self._api_endpoint(
            getattr(settings, 'academic_ap_get_data_cms_endpoint', '/get-data-cms'),
            '/get-data-cms',
        )
        with httpx.Client(timeout=self.timeout_seconds, verify=self._verify_config(endpoint)) as http:
            response = http.post(endpoint, headers=self._headers(), json=body)
            response.raise_for_status()
            data = response.json()
        self._ensure_success_response(data, label=f'AP get-data-cms {body["subject_code"]}')
        payload = data.get('data') if isinstance(data, dict) else data
        if not isinstance(payload, dict):
            raise RuntimeError(f'AP get-data-cms trả payload không hợp lệ cho {body["subject_code"]}.')
        return payload


"""
client = replace_block(client, '    def get_division(', '\n\nclass AcademicImportService:', division_block, 'keyless data API method')

# New cache/source naming and endpoint metadata.
client = client.replace("'/tmp/ai-server-ap-cache/get-course'", "'/tmp/ai-server-ap-cache/get-all-subject'")
client = client.replace("ap.get-course.file-cache", "ap.get-all-subject.file-cache")
client = client.replace("ap.get-course", "ap.get-all-subject")
client = client.replace("AP get-course", "AP get-all-subject")
client = client.replace("academic_ap_get_course_endpoint', '/get-course'", "academic_ap_get_all_subject_endpoint', '/get-all-subject'")

old_campus_options = """        campuses = self._campus_master_values(branch=normalized_branch)
        if not campuses:
            warnings.append('Chưa có cơ sở đang dùng cho hệ này. Vào /premises để thêm hoặc bật cơ sở trước khi đồng bộ AP.')
"""
new_campus_options = """        try:
            remote_campuses = APAcademicClient().get_campuses(branch=normalized_branch)
            campuses = [
                {
                    'value': item['campus_code'],
                    'label': item.get('campus_name') or item['campus_code'].upper(),
                    'description': f\"Danh mục nội bộ · {item.get('product') or normalized_branch.upper()}\",
                    'meta': {
                        'source': 'ap.get-campus',
                        'product': item.get('product'),
                        'api_value': item.get('api_value'),
                    },
                }
                for item in remote_campuses
            ]
        except Exception:
            campuses = self._campus_master_values(branch=normalized_branch)
            if campuses:
                warnings.append('Không tải được danh sách cơ sở từ API nội bộ; tạm dùng danh mục cơ sở đã lưu.')
            else:
                warnings.append('Không tải được danh sách cơ sở từ API nội bộ và chưa có danh mục cơ sở dự phòng.')
"""
client = replace_once(client, old_campus_options, new_campus_options, 'AP options campus source')
client = client.replace(
    "Campuses come only from rows maintained manually in /premises. Subjects\n        are resolved from api_v2 /get-course with branch=poly and the selected\n        term_name, with local DB/env fallback if that endpoint is unavailable.",
    "Campuses come from keyless /get-campus?product=POLY|PTCD. Subjects come\n        from keyless /get-all-subject. Existing DB/env data is fallback only so\n        the operator keeps one simple set of dropdowns when the API is unavailable.",
)
client = client.replace(
    "Không tải được danh sách môn từ AP get-all-subject, đang dùng dữ liệu môn đã lưu nếu có.",
    "Không tải được danh sách môn từ API nội bộ get-all-subject; đang dùng dữ liệu môn đã lưu nếu có.",
)
client_path.write_text(client)


# ---------------------------------------------------------------------------
# 3) Route help text: describe the same simple dropdowns and new sources.
# ---------------------------------------------------------------------------
route_path = Path('backend/app/api/routes/academic.py')
route = route_path.read_text()
route = route.replace(
    "campus: str | None = Query(None, description='Giữ tương thích UI cũ. Cơ sở lấy từ danh mục nhập thủ công; danh sách môn lấy từ api_v2 /get-course với branch=poly và term_name đã chọn.'),",
    "campus: str | None = Query(None, description='Giữ tương thích UI cũ. Cơ sở lấy từ get-campus theo POLY/PTCD; môn lấy từ get-all-subject. Hai API nội bộ không dùng API key.'),",
)
route_path.write_text(route)


# ---------------------------------------------------------------------------
# 4) Env examples: make the deploy contract explicit and remove stale key/TLS host.
# ---------------------------------------------------------------------------
new_env_block = """# Academic sync through Polytechnic internal CMS API (keyless)
ACADEMIC_AP_SYNC_ENABLED=true
ACADEMIC_AP_API_BASE_URL=https://api.poly.edu.vn/api/cms
# POST dữ liệu lớp/sinh viên
ACADEMIC_AP_GET_DATA_CMS_ENDPOINT=/get-data-cms
# GET danh sách môn
ACADEMIC_AP_GET_ALL_SUBJECT_ENDPOINT=/get-all-subject
# GET cơ sở với product=POLY hoặc product=PTCD
ACADEMIC_AP_GET_CAMPUS_ENDPOINT=/get-campus
# Legacy compatibility only; canonical internal API does not send Authorization.
ACADEMIC_AP_API_KEY=
ACADEMIC_AP_REQUEST_TIMEOUT_SECONDS=60
ACADEMIC_AP_TLS_MODE=strict
# Existing cache knobs retained; cache content now comes from get-all-subject.
ACADEMIC_AP_GET_COURSE_FILE_CACHE_ENABLED=true
ACADEMIC_AP_GET_COURSE_FILE_CACHE_DIR=/tmp/ai-server-ap-cache/get-all-subject
ACADEMIC_AP_GET_COURSE_FILE_CACHE_TTL_SECONDS=86400
ACADEMIC_AP_GET_COURSE_FILE_CACHE_REFRESH=false
ACADEMIC_AP_TERM_BLOCK_REFRESH_TTL_SECONDS=3600
# Optional local subject fallback if the internal catalog is temporarily unavailable.
ACADEMIC_AP_SUBJECT_CODES=

"""
for env_name in ('.env.example', '.env.production.example'):
    path = Path(env_name)
    text = path.read_text()
    start = text.find('# v25.9.16 Academic AP sync credentials')
    if start < 0:
        raise RuntimeError(f'{env_name}: AP section start not found')
    end = text.find('# v25.9.16.5.8 Student Management', start)
    if end < 0:
        raise RuntimeError(f'{env_name}: AP section end not found')
    path.write_text(text[:start] + new_env_block + text[end:])


# ---------------------------------------------------------------------------
# 5) Regression tests for exact HTTP contract and no secret leakage.
# ---------------------------------------------------------------------------
test_path = Path('backend/app/tests/test_academic_ap_internal_api.py')
test_path.write_text(r'''from __future__ import annotations

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


def test_get_all_subject_is_global_keyless_catalog():
    subjects = make_client().get_subjects(branch='poly', term_name='Fall 2026')
    assert [item['subject_code'] for item in subjects] == ['AUT218', 'MEC229']
    call = FakeHttpClient.calls[-1]
    assert call['method'] == 'GET'
    assert call['url'] == 'https://api.poly.edu.vn/api/cms/get-all-subject'
    assert not call.get('params')
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
''')

print('AP internal API migration patch applied')
