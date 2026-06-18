from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import settings


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


def _canonical(method: str, path: str, timestamp: str, nonce: str, raw_body: bytes) -> str:
    body_hash = hashlib.sha256(raw_body).hexdigest()
    return '\n'.join([method.upper(), path, timestamp, nonce, body_hash])


class OpenEdXStudentInsightClient:
    """Client for the future LMS plugin `openedx_ai_student_insight`.

    v25.9.16.1 uses this only for AP username -> Open edX username mapping.
    The API contract is intentionally the same as the planned LMS plugin:
    POST /api/ai-student-insight/v1/users/resolve
    """

    def __init__(self) -> None:
        base = (settings.openedx_student_insight_base_url or settings.openedx_lms_base_url or '').rstrip('/')
        self.base_url = base
        self.endpoint = settings.openedx_student_insight_users_resolve_endpoint or '/api/ai-student-insight/v1/users/resolve'
        self.timeout_seconds = settings.openedx_student_insight_timeout_seconds
        self.client_id = settings.openedx_student_insight_client_id or 'ai-server'
        self.shared_secret = settings.openedx_student_insight_shared_secret or settings.openedx_connector_hmac_secret

    def configured(self) -> bool:
        return bool(self.base_url and self.shared_secret)

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

        This is a synchronous, small counterpart of the normal Open edX connector
        auth path. It is used only for lightweight lookups such as course search
        so operators do not have to manually sync CourseSyncState before Academic
        course mapping can work.
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

    def _headers(self, method: str, path: str, raw_body: bytes) -> dict[str, str]:
        if not self.shared_secret:
            raise RuntimeError('OPENEDX_STUDENT_INSIGHT_SHARED_SECRET hoặc OPENEDX_CONNECTOR_HMAC_SECRET chưa cấu hình')
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        nonce = str(uuid.uuid4())
        canonical = _canonical(method, path, timestamp, nonce, raw_body)
        signature = hmac.new(self.shared_secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        return {
            'Content-Type': 'application/json',
            'X-AI-Client': self.client_id,
            'X-AI-Timestamp': timestamp,
            'X-AI-Nonce': nonce,
            'X-AI-Signature': signature,
        }


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
                normalized = OpenEdXStudentInsightClient._normalize_course_item(item)
                if normalized:
                    results.append(normalized)
        return results

    def _search_courses_via_student_insight(self, *, query: str, exact_course_id: str | None, limit: int) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        endpoint = getattr(settings, 'openedx_student_insight_course_search_endpoint', '/api/ai-student-insight/v1/courses/search')
        path = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        body = {'query': query, 'exact_course_id': exact_course_id, 'limit': limit}
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        url = urljoin(self.base_url + '/', path.lstrip('/'))
        headers = self._headers('POST', path, raw)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, content=raw, headers=headers)
            # Not all deployments have the future plugin endpoint yet. Treat 404 as
            # unavailable and fall through to the public/standard Courses API.
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
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

    def search_courses(self, *, query: str, exact_course_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Search Open edX courses using API-first fallbacks.

        Priority:
        1. Student Insight/CMS plugin course search if installed.
        2. Standard LMS Courses API.

        Callers should treat an empty list as "API unavailable or no match" and
        keep the page usable; this method is for auto-fill, not a hard dependency.
        """
        cleaned_query = str(query or exact_course_id or '').strip()
        if not cleaned_query:
            return []
        limit = max(1, min(int(limit or 10), 50))
        try:
            results = self._search_courses_via_student_insight(query=cleaned_query, exact_course_id=exact_course_id, limit=limit)
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
            return str(exact[0]['course_id']), exact[0].get('display_name'), 1, 'openedx_api'
        return None, None, len(exact), 'openedx_api' if results else 'unavailable'

    def resolve_users(self, students: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError('Chưa cấu hình Open edX Student Insight plugin/HMAC để resolve user')
        path = self.endpoint if self.endpoint.startswith('/') else f'/{self.endpoint}'
        body = {'students': students}
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        url = urljoin(self.base_url + '/', path.lstrip('/'))
        headers = self._headers('POST', path, raw)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, content=raw, headers=headers)
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            results = data.get('results')
            if isinstance(results, list):
                return results
            # Accept the compact contract often used by simple Open edX plugins:
            # {found: [{username/user_id/...}], missing: ["he..."]}.
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
        raise RuntimeError('Open edX Student Insight trả về dữ liệu không hợp lệ')
