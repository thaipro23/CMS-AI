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
            return data.get('results') or []
        if isinstance(data, list):
            return data
        raise RuntimeError('Open edX Student Insight trả về dữ liệu không hợp lệ')
