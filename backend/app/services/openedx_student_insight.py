from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from app.core.config import settings


CONNECTOR_PREFIX = '/api/ai-connector/v1'
LEGACY_STUDENT_INSIGHT_PREFIX = '/api/ai-student-insight/v1'


def normalize_username(value: Any) -> str:
    return str(value or '').strip().lower()


def mask_email(value: Any) -> str | None:
    raw = str(value or '').strip()
    if not raw or '@' not in raw:
        return raw or None
    name, domain = raw.split('@', 1)
    if len(name) <= 2:
        masked = name[0:1] + '***'
    else:
        masked = f'{name[:2]}***{name[-1:]}'
    return f'{masked}@{domain}'


def _path(value: str | None, default: str) -> str:
    raw = str(value or default or '').strip() or default
    return raw if raw.startswith('/') else f'/{raw}'


def _legacy_path(connector_path: str) -> str:
    path = _path(connector_path, connector_path)
    if path.startswith(CONNECTOR_PREFIX):
        return LEGACY_STUDENT_INSIGHT_PREFIX + path[len(CONNECTOR_PREFIX):]
    return path


class OpenEdXConnectorClient:
    """Unified AI Server -> openedx_connector_plugin client.

    Canonical runtime API lives in the existing Open edX connector plugin on the
    LMS Django host, under /api/ai-connector/v1/*.

    The old /api/ai-student-insight/v1/* namespace is kept only as a deployment
    compatibility fallback. New deployments should configure:
      OPENEDX_CONNECTOR_BASE_URL=http(s)://<LMS-host>
      OPENEDX_CONNECTOR_HMAC_SECRET=<same secret in Tutor LMS/CMS>
    """

    def __init__(self) -> None:
        base = (
            getattr(settings, 'openedx_connector_base_url', None)
            or settings.openedx_student_insight_base_url
            or settings.openedx_lms_base_url
            or ''
        ).rstrip('/')
        self.base_url = base
        self.users_resolve_endpoint = _path(
            getattr(settings, 'openedx_connector_users_resolve_endpoint', None),
            '/api/ai-connector/v1/users/resolve',
        )
        self.course_search_endpoint = _path(
            getattr(settings, 'openedx_connector_course_search_endpoint', None),
            '/api/ai-connector/v1/courses/search',
        )
        self.class_analytics_endpoint = _path(
            getattr(settings, 'openedx_connector_class_analytics_endpoint', None),
            '/api/ai-connector/v1/class-analytics',
        )
        self.enrollment_enroll_endpoint = _path(
            getattr(settings, 'openedx_connector_enrollment_enroll_endpoint', None),
            '/api/ai-connector/v1/course-enrollment/enroll',
        )
        self.timeout_seconds = int(
            getattr(settings, 'openedx_connector_timeout_seconds', None)
            or getattr(settings, 'openedx_student_insight_timeout_seconds', 30)
            or 30
        )
        self.client_id = (
            getattr(settings, 'openedx_connector_client_id', None)
            or getattr(settings, 'openedx_student_insight_client_id', None)
            or 'ai-server'
        )
        self.connector_secret = (
            settings.openedx_connector_hmac_secret
            or getattr(settings, 'openedx_student_insight_shared_secret', None)
            or ''
        )
        # Backward-compatible public attribute used by older one-off debug scripts.
        self.shared_secret = self.connector_secret
        # Backward-compatible public attribute used by older one-off debug scripts.
        self.endpoint = self.users_resolve_endpoint

    def configured(self) -> bool:
        return bool(self.base_url and self.connector_secret)

    @staticmethod
    def _infer_token_type(token: str | None) -> str | None:
        if not token:
            return None
        return 'JWT' if token.count('.') == 2 else 'Bearer'

    @staticmethod
    def _normalize_auth_scheme(token_type: str | None) -> str:
        value = (token_type or 'Bearer').strip()
        if value.lower() == 'jwt':
            return 'JWT'
        if value.lower() == 'bearer':
            return 'Bearer'
        return value

    def _oauth_headers(self) -> dict[str, str]:
        """Build Authorization headers for standard LMS/CMS APIs.

        Connector/HMAC is preferred for production academic operations. This
        OAuth fallback remains only for read-only standard Open edX course API
        lookups when the connector endpoint is not deployed yet.
        """
        token = settings.openedx_access_token
        token_type = self._infer_token_type(token)
        if not token and settings.openedx_client_id and settings.openedx_client_secret:
            oauth_base = (settings.openedx_oauth_base_url or settings.openedx_lms_base_url or settings.openedx_base_url or '').rstrip('/')
            token_url = f'{oauth_base}{settings.openedx_oauth_token_url}'
            with httpx.Client(timeout=settings.openedx_request_timeout_seconds) as client:
                response = client.post(
                    token_url,
                    data={
                        'grant_type': 'client_credentials',
                        'client_id': settings.openedx_client_id,
                        'client_secret': settings.openedx_client_secret,
                        'token_type': 'jwt',
                        'scope': 'read write',
                    },
                )
                response.raise_for_status()
                payload = response.json()
            token = payload.get('access_token')
            token_type = payload.get('token_type') or self._infer_token_type(token)
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = f'{self._normalize_auth_scheme(token_type)} {token}'
        return headers

    def _headers(self, method: str, path: str, raw_body: bytes, *, use_nonce: bool = True) -> dict[str, str]:
        if not self.connector_secret:
            raise RuntimeError('OPENEDX_CONNECTOR_HMAC_SECRET chưa cấu hình cho AI Server')
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        body_hash = hashlib.sha256(raw_body).hexdigest()
        normalized_path = _path(path, path)
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-AI-Client': self.client_id,
            'X-AI-Connector-Timestamp': timestamp,
        }
        if use_nonce:
            nonce = str(uuid.uuid4())
            # v25.9.16.5.8 adds nonce to the connector canonical string. The Open edX
            # plugin still accepts the old four-part canonical form for rolling upgrades,
            # but nonce prevents duplicate signatures for identical requests inside the
            # same second.
            canonical = f'{timestamp}.{method.upper()}.{normalized_path}.{body_hash}.{nonce}'
            headers['X-AI-Connector-Nonce'] = nonce
        else:
            # Rolling-upgrade fallback for older openedx_connector_plugin versions.
            canonical = f'{timestamp}.{method.upper()}.{normalized_path}.{body_hash}'
        signature = hmac.new(
            self.connector_secret.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        headers['X-AI-Connector-Signature'] = signature
        return headers

    def _raise_for_status_with_context(self, response: httpx.Response, *, operation: str, path: str) -> None:
        if response.status_code < 400:
            return
        plugin_message = ''
        plugin_code = ''
        try:
            data = response.json()
            if isinstance(data, dict):
                plugin_message = str(data.get('message') or data.get('detail') or data.get('error') or '')
                plugin_code = str(data.get('code') or data.get('status') or '')
        except Exception:
            plugin_message = (response.text or '')[:500]
        if response.status_code == 403:
            text_l = (response.text or '').lower()
            if '<html' in text_l and ('csrf' in text_l or 'forbidden' in text_l):
                raise RuntimeError(
                    f'Open edX Connector bị Django từ chối trước khi vào view khi {operation}: 403 Forbidden tại {path}. '
                    'Body trả về là HTML 403, thường do endpoint server-to-server chưa được csrf_exempt hoặc Open edX đang chạy plugin cũ. '
                    'Hãy cập nhật openedx_connector_plugin bản mới vào LMS/CMS, rebuild/restart lms cms lms-worker cms-worker, '
                    'sau đó test lại /api/ai-connector/v1/users/resolve. '
                    f'Chi tiết rút gọn: {plugin_message or plugin_code or "không có body"}.'
                )
            raise RuntimeError(
                f'Open edX Connector bị từ chối HMAC khi {operation}: 403 Forbidden tại {path}. '
                f'Chi tiết plugin: {plugin_message or plugin_code or "không có body"}. '
                'Kiểm tra OPENEDX_CONNECTOR_HMAC_SECRET ở AI Server phải giống AI_CONNECTOR_HMAC_SECRET trong Tutor LMS/CMS, '
                'và OPENEDX_CONNECTOR_BASE_URL phải trỏ tới LMS Django, không phải MFE.'
            )
        response.raise_for_status()

    def _post_json(self, *, path: str, body: dict[str, Any], operation: str, timeout: int | None = None, legacy_fallback: bool = True) -> Any:
        if not self.configured():
            raise RuntimeError('Chưa cấu hình OPENEDX_CONNECTOR_BASE_URL/OPENEDX_CONNECTOR_HMAC_SECRET để gọi Open edX Connector')
        primary = _path(path, path)
        candidates = [primary]
        legacy = _legacy_path(primary)
        if legacy_fallback and legacy != primary:
            candidates.append(legacy)
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        last_404: httpx.Response | None = None
        for candidate_path in candidates:
            url = urljoin(self.base_url + '/', candidate_path.lstrip('/'))
            headers = self._headers('POST', candidate_path, raw, use_nonce=True)
            with httpx.Client(timeout=timeout or self.timeout_seconds) as client:
                response = client.post(url, content=raw, headers=headers)
                # Rolling-upgrade fallback: older connector plugins validate the
                # four-part connector HMAC canonical string and do not know the
                # X-AI-Connector-Nonce extension yet. Retry once without nonce if
                # the nonce-signed request is rejected.
                if response.status_code == 403:
                    legacy_headers = self._headers('POST', candidate_path, raw, use_nonce=False)
                    legacy_response = client.post(url, content=raw, headers=legacy_headers)
                    if legacy_response.status_code < 400 or legacy_response.status_code == 404:
                        response = legacy_response
            if response.status_code == 404 and candidate_path != candidates[-1]:
                last_404 = response
                continue
            self._raise_for_status_with_context(response, operation=operation, path=candidate_path)
            return response.json()
        if last_404 is not None:
            self._raise_for_status_with_context(last_404, operation=operation, path=primary)
        return None

    @staticmethod
    def _normalize_course_item(item: dict[str, Any]) -> dict[str, Any] | None:
        course_id = str(
            item.get('course_id')
            or item.get('id')
            or item.get('key')
            or item.get('course_key')
            or item.get('course')
            or ''
        ).strip()
        if not course_id:
            return None
        title = str(
            item.get('display_name')
            or item.get('name')
            or item.get('course_name')
            or item.get('title')
            or ''
        ).strip() or None
        return {'course_id': course_id, 'display_name': title, 'raw': item}

    @staticmethod
    def _extract_course_results(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = data.get('results') or data.get('courses') or data.get('data') or data.get('items') or []
        else:
            raw_items = []
        results: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                normalized = OpenEdXConnectorClient._normalize_course_item(item)
                if normalized:
                    results.append(normalized)
        return results

    def _search_courses_via_connector(self, *, query: str, exact_course_id: str | None, limit: int) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        body = {'query': query, 'exact_course_id': exact_course_id, 'limit': limit}
        data = self._post_json(path=self.course_search_endpoint, body=body, operation='search Course CMS', timeout=self.timeout_seconds)
        return self._extract_course_results(data)

    def _search_courses_via_lms_courses_api(self, *, query: str, limit: int) -> list[dict[str, Any]]:
        base = (settings.openedx_lms_base_url or settings.openedx_base_url or '').rstrip('/')
        if not base:
            return []
        endpoint = getattr(settings, 'openedx_courses_search_endpoint', '/api/courses/v1/courses/')
        path = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        url = urljoin(base + '/', path.lstrip('/'))
        params = {'search_term': query, 'page_size': str(max(1, min(limit, 50)))}
        headers = self._oauth_headers()
        with httpx.Client(timeout=settings.openedx_request_timeout_seconds) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        return self._extract_course_results(data)

    def _get_course_via_lms_courses_api_exact(self, *, course_id: str) -> dict[str, Any] | None:
        base = (settings.openedx_lms_base_url or settings.openedx_base_url or '').rstrip('/')
        if not base or not course_id:
            return None
        endpoint = getattr(settings, 'openedx_courses_search_endpoint', '/api/courses/v1/courses/')
        path = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        if not path.endswith('/'):
            path += '/'
        url = urljoin(base + '/', f"{path.lstrip('/')}{quote(course_id, safe='')}/")
        headers = self._oauth_headers()
        with httpx.Client(timeout=settings.openedx_request_timeout_seconds) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            self._raise_for_status_with_context(response, operation='get exact Course CMS', path=f'{path}{course_id}/')
            data = response.json()
        if isinstance(data, dict):
            return self._normalize_course_item(data)
        return None

    def search_courses(self, *, query: str, exact_course_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Search Open edX courses using connector-first fallbacks."""
        cleaned_query = str(query or exact_course_id or '').strip()
        if not cleaned_query:
            return []
        limit = max(1, min(int(limit or 10), 50))
        try:
            results = self._search_courses_via_connector(query=cleaned_query, exact_course_id=exact_course_id, limit=limit)
            if results:
                return results[:limit]
        except Exception:
            pass
        try:
            results = self._search_courses_via_lms_courses_api(query=cleaned_query, limit=limit)
            if results:
                return results[:limit]
        except Exception:
            pass
        return []

    def find_exact_course(self, course_id: str) -> tuple[str | None, str | None, int, str]:
        target = str(course_id or '').strip()
        if not target:
            return None, None, 0, 'empty'

        results = self.search_courses(query=target, exact_course_id=target, limit=10)
        exact = [item for item in results if str(item.get('course_id') or '').strip().lower() == target.lower()]
        if len(exact) == 1:
            return str(exact[0]['course_id']), exact[0].get('display_name'), 1, 'openedx_connector_course_search'
        if len(exact) > 1:
            return None, None, len(exact), 'openedx_connector_course_search'

        try:
            item = self._get_course_via_lms_courses_api_exact(course_id=target)
            if item and str(item.get('course_id') or '').strip().lower() == target.lower():
                return str(item['course_id']), item.get('display_name'), 1, 'lms_courses_api_exact'
        except Exception:
            pass

        return None, None, len(exact), 'openedx_connector_api_unavailable_or_not_found'

    def class_analytics(self, *, course_id: str, students: list[dict[str, Any]], cohort_name: str | None = None) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError('Chưa cấu hình Open edX Connector/HMAC để lấy tiến độ/điểm CMS')
        body = {'course_id': course_id, 'cohort_name': cohort_name, 'students': students}
        data = self._post_json(
            path=self.class_analytics_endpoint,
            body=body,
            operation='lấy tiến độ/điểm CMS',
            timeout=max(self.timeout_seconds, 60),
        )
        if isinstance(data, dict):
            rows = data.get('results') or data.get('items') or data.get('students') or []
            return rows if isinstance(rows, list) else []
        if isinstance(data, list):
            return data
        raise RuntimeError('Open edX Connector class analytics trả về dữ liệu không hợp lệ')

    def enroll_users(self, *, course_id: str, students: list[dict[str, Any]], teachers: list[dict[str, Any]] | None = None, mode: str | None = None, force: bool = False, cohort_name: str | None = None, create_missing: bool = False) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError('Chưa cấu hình Open edX Connector/HMAC để enroll sinh viên vào Course CMS')
        default_mode = (
            getattr(settings, 'openedx_connector_default_enrollment_mode', None)
            or getattr(settings, 'openedx_student_insight_default_enrollment_mode', 'audit')
            or 'audit'
        )
        body = {
            'course_id': course_id,
            'mode': mode or default_mode,
            'force': bool(force),
            'cohort_name': cohort_name,
            'create_missing': bool(create_missing),
            'students': students,
            'teachers': teachers or [],
        }
        data = self._post_json(
            path=self.enrollment_enroll_endpoint,
            body=body,
            operation='enroll Course CMS',
            timeout=max(self.timeout_seconds, 60),
        )
        if isinstance(data, dict):
            rows = data.get('results') or data.get('items') or data.get('students') or []
            return rows if isinstance(rows, list) else []
        if isinstance(data, list):
            return data
        raise RuntimeError('Open edX Connector enrollment trả về dữ liệu không hợp lệ')

    def resolve_users(self, students: list[dict[str, Any]], *, create_missing: bool = False) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError('Chưa cấu hình Open edX Connector/HMAC để resolve/create user')
        body = {'students': students, 'create_missing': bool(create_missing)}
        data = self._post_json(
            path=self.users_resolve_endpoint,
            body=body,
            operation='tạo/kiểm tra user CMS',
            timeout=self.timeout_seconds,
        )
        if isinstance(data, dict):
            results = data.get('results')
            if isinstance(results, list):
                return results
            normalized: list[dict[str, Any]] = []
            found = data.get('found') or []
            if isinstance(found, list):
                for item in found:
                    if isinstance(item, dict):
                        username = normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username'))
                        normalized.append({
                            **item,
                            'ap_username': username,
                            'username': username,
                            'exists': True,
                            'match_status': item.get('match_status') or ('inactive' if item.get('is_active') is False or item.get('openedx_is_active') is False else 'matched'),
                            'match_method': item.get('match_method') or 'exact_ap_username',
                            'openedx_user_id': item.get('openedx_user_id') or item.get('user_id') or item.get('id'),
                            'openedx_username': item.get('openedx_username') or item.get('username'),
                            'openedx_email': item.get('openedx_email') or item.get('email'),
                        })
            missing = data.get('missing') or []
            if isinstance(missing, list):
                for value in missing:
                    if isinstance(value, dict):
                        username = normalize_username(value.get('ap_username') or value.get('username'))
                        student_code = value.get('student_code') or value.get('studentCode')
                    else:
                        username = normalize_username(value)
                        student_code = None
                    if username:
                        normalized.append({
                            'ap_username': username,
                            'username': username,
                            'student_code': student_code,
                            'exists': False,
                            'match_status': 'missing',
                            'match_method': 'not_found',
                            'note': 'Không tìm thấy user CMS/Open edX theo AP username',
                        })
            if normalized:
                return normalized
            return []
        if isinstance(data, list):
            return data
        raise RuntimeError('Open edX Connector trả về dữ liệu không hợp lệ')


# Backward-compatible alias. Existing AcademicService imports keep working while
# operators migrate env names from OPENEDX_STUDENT_INSIGHT_* to OPENEDX_CONNECTOR_*.
OpenEdXStudentInsightClient = OpenEdXConnectorClient
