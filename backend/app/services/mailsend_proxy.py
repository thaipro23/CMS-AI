from __future__ import annotations

import time
from typing import Any, Callable
from urllib.parse import quote

import httpx

from app.core.config import settings


TERMINAL_STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED'}


class MailSendProxyError(RuntimeError):
    """Safe Mail Send error that never embeds the ProxyKey or recipients."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        raise MailSendProxyError(
            'MAILSEND_INVALID_RESPONSE',
            'Mail Send trả dữ liệu không đúng định dạng JSON.',
        ) from exc
    if not isinstance(payload, dict):
        raise MailSendProxyError(
            'MAILSEND_INVALID_RESPONSE',
            'Mail Send trả dữ liệu không đúng cấu trúc.',
        )
    nested = payload.get('data')
    if isinstance(nested, dict):
        return {**payload, **nested}
    return payload


def _status_value(payload: dict[str, Any]) -> str:
    return str(payload.get('status') or payload.get('sessionStatus') or '').strip().upper()


class MailSendProxyClient:
    """Small client for Polytechnic Mail Send's ProxyKey bulk-session API.

    Text form fields are deliberately sent as multipart parts with no filename.
    Repeating ``sourceTo.inlineEmails`` preserves the API's email-array contract.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        create_path: str | None = None,
        status_path: str | None = None,
        request_timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        poll_timeout_seconds: float | None = None,
        max_recipients: int | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = str(base_url or settings.mailsend_proxy_base_url).strip().rstrip('/')
        self.api_key = str(api_key if api_key is not None else settings.mailsend_proxy_api_key or '').strip()
        self.create_path = str(create_path or settings.mailsend_proxy_create_path).strip()
        self.status_path = str(status_path or settings.mailsend_proxy_status_path).strip()
        self.request_timeout_seconds = max(
            1.0,
            float(request_timeout_seconds or settings.mailsend_request_timeout_seconds),
        )
        self.poll_interval_seconds = max(
            0.2,
            float(poll_interval_seconds or settings.mailsend_poll_interval_seconds),
        )
        self.poll_timeout_seconds = max(
            self.poll_interval_seconds,
            float(poll_timeout_seconds or settings.mailsend_poll_timeout_seconds),
        )
        self.max_recipients = max(
            1,
            min(1000, int(max_recipients or settings.mailsend_max_recipients or 1000)),
        )
        self._client = http_client

    @property
    def configured(self) -> bool:
        return bool(settings.mailsend_enabled and self.base_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise MailSendProxyError(
                'MAILSEND_NOT_CONFIGURED',
                'AI Server chưa được cấu hình Mail Send ProxyKey.',
            )
        return {'X-API-Key': self.api_key, 'Accept': 'application/json'}

    def _url(self, path: str) -> str:
        clean_path = path if path.startswith('/') else f'/{path}'
        return f'{self.base_url}{clean_path}'

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.request(method, url, timeout=self.request_timeout_seconds, **kwargs)
            with httpx.Client(timeout=self.request_timeout_seconds, follow_redirects=False) as client:
                return client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise MailSendProxyError(
                'MAILSEND_TIMEOUT',
                'Mail Send không phản hồi trong thời gian cho phép.',
            ) from exc
        except httpx.HTTPError as exc:
            raise MailSendProxyError(
                'MAILSEND_UNAVAILABLE',
                'Không kết nối được tới Mail Send.',
            ) from exc

    def create_bulk_session(
        self,
        *,
        subject: str,
        body_template: str,
        emails: list[str],
    ) -> dict[str, Any]:
        unique_emails = list(dict.fromkeys(str(item or '').strip().lower() for item in emails if str(item or '').strip()))
        if not unique_emails:
            raise MailSendProxyError('MAILSEND_NO_RECIPIENTS', 'Không có email hợp lệ để gửi.')
        if len(unique_emails) > self.max_recipients:
            raise MailSendProxyError(
                'MAILSEND_RECIPIENT_LIMIT',
                f'Mỗi session Mail Send chỉ nhận tối đa {self.max_recipients} người.',
            )
        multipart_parts: list[tuple[str, tuple[None, str]]] = [
            ('subject', (None, subject)),
            ('bodyTemplate', (None, body_template)),
        ]
        multipart_parts.extend(('sourceTo.inlineEmails', (None, email)) for email in unique_emails)
        response = self._request(
            'POST',
            self._url(self.create_path),
            headers=self._headers(),
            files=multipart_parts,
        )
        if response.status_code != 202:
            raise MailSendProxyError(
                'MAILSEND_CREATE_REJECTED',
                f'Mail Send từ chối tạo session (HTTP {response.status_code}).',
            )
        payload = _response_payload(response)
        session_id = str(payload.get('sessionId') or payload.get('id') or '').strip()
        if not session_id:
            raise MailSendProxyError(
                'MAILSEND_SESSION_ID_MISSING',
                'Mail Send đã nhận yêu cầu nhưng không trả sessionId.',
            )
        return {
            'session_id': session_id,
            'status': _status_value(payload) or 'QUEUED',
            'max_recipients': payload.get('maxRecipients'),
        }

    def get_bulk_session(self, session_id: str) -> dict[str, Any]:
        clean_id = str(session_id or '').strip()
        if not clean_id:
            raise MailSendProxyError('MAILSEND_SESSION_ID_MISSING', 'Thiếu sessionId Mail Send.')
        path = self.status_path.format(session_id=quote(clean_id, safe=''))
        response = self._request(
            'GET',
            self._url(path),
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise MailSendProxyError(
                'MAILSEND_STATUS_REJECTED',
                f'Không đọc được trạng thái Mail Send (HTTP {response.status_code}).',
            )
        payload = _response_payload(response)
        return {
            'session_id': str(payload.get('sessionId') or payload.get('id') or clean_id),
            'status': _status_value(payload),
            'sent_count': payload.get('sentCount'),
            'failed_count': payload.get('failedCount'),
            'total_count': payload.get('totalCount') or payload.get('recipientCount'),
            'finished_at': payload.get('finishedAt'),
        }

    def wait_for_terminal(
        self,
        session_id: str,
        *,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> dict[str, Any]:
        deadline = monotonic() + self.poll_timeout_seconds
        last_status: dict[str, Any] | None = None
        while monotonic() <= deadline:
            last_status = self.get_bulk_session(session_id)
            if on_status is not None:
                on_status(last_status)
            status = str(last_status.get('status') or '').upper()
            if status in TERMINAL_STATUSES or last_status.get('finished_at') is not None:
                if status not in TERMINAL_STATUSES:
                    raise MailSendProxyError(
                        'MAILSEND_UNKNOWN_TERMINAL_STATUS',
                        'Mail Send kết thúc với trạng thái không được hỗ trợ.',
                    )
                return last_status
            sleep(self.poll_interval_seconds)
        raise MailSendProxyError(
            'MAILSEND_POLL_TIMEOUT',
            'Hết thời gian chờ Mail Send xác nhận kết quả; session chưa được đánh dấu đã gửi.',
        )
