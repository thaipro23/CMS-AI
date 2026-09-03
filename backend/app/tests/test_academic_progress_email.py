from pathlib import Path

import httpx
import pytest

from app.services.academic.progress_email import mask_recipient_email, plain_text_mail_template
from app.services.mailsend_proxy import MailSendProxyClient, MailSendProxyError


def test_mail_send_proxy_creates_multipart_session_and_polls_to_completed():
    requests: list[httpx.Request] = []
    status_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_calls
        requests.append(request)
        if request.method == 'POST':
            assert request.url.path == '/api/proxy/bulk-sessions/with-files'
            assert request.headers['X-API-Key'] == 'proxy-secret'
            assert request.headers['Content-Type'].startswith('multipart/form-data; boundary=')
            content = request.read()
            assert b'name="subject"' in content
            assert b'name="bodyTemplate"' in content
            assert content.count(b'name="sourceTo.inlineEmails"') == 2
            assert b'sv001@example.edu.vn' in content
            assert b'sv002@example.edu.vn' in content
            return httpx.Response(202, json={'sessionId': 'session-123', 'status': 'QUEUED'})

        status_calls += 1
        assert request.method == 'GET'
        assert request.url.path == '/api/proxy/bulk-sessions/session-123'
        if status_calls == 1:
            return httpx.Response(200, json={'sessionId': 'session-123', 'status': 'QUEUED'})
        return httpx.Response(
            200,
            json={
                'sessionId': 'session-123',
                'status': 'COMPLETED',
                'sentCount': 2,
                'failedCount': 0,
                'finishedAt': '2026-09-03T12:00:00Z',
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = MailSendProxyClient(
            base_url='https://mailsend.example.test',
            api_key='proxy-secret',
            http_client=http_client,
            poll_interval_seconds=0.2,
            poll_timeout_seconds=5,
        )
        created = client.create_bulk_session(
            subject='Nhắc tiến độ',
            body_template='<p>Xin chào {{maHs}}</p>',
            emails=['SV001@example.edu.vn', 'sv002@example.edu.vn', 'sv001@example.edu.vn'],
        )
        terminal = client.wait_for_terminal(
            created['session_id'],
            sleep=lambda _seconds: None,
            monotonic=lambda: 0,
        )

    assert created == {'session_id': 'session-123', 'status': 'QUEUED', 'max_recipients': None}
    assert terminal['status'] == 'COMPLETED'
    assert terminal['sent_count'] == 2
    assert [request.method for request in requests] == ['POST', 'GET', 'GET']


def test_mail_send_proxy_error_does_not_leak_key_or_recipient():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text='proxy-secret failed for private-student@example.edu.vn',
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = MailSendProxyClient(
            base_url='https://mailsend.example.test',
            api_key='proxy-secret',
            http_client=http_client,
        )
        with pytest.raises(MailSendProxyError) as caught:
            client.create_bulk_session(
                subject='Nhắc tiến độ',
                body_template='<p>Nội dung</p>',
                emails=['private-student@example.edu.vn'],
            )

    public_error = str(caught.value)
    assert caught.value.code == 'MAILSEND_CREATE_REJECTED'
    assert 'proxy-secret' not in public_error
    assert 'private-student@example.edu.vn' not in public_error


def test_progress_email_helpers_mask_address_and_escape_teacher_text():
    assert mask_recipient_email('student01@fpt.edu.vn') == 's***1@fpt.edu.vn'
    rendered = plain_text_mail_template('Xin chào {{maHs}}\n<script>alert(1)</script>')
    assert '{{maHs}}' in rendered
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert '<br>' in rendered


def test_worker_refreshes_cms_before_creating_mail_send_session():
    root = Path(__file__).resolve().parents[1]
    worker = (root / 'worker.py').read_text(encoding='utf-8')
    start = worker.index("@celery_app.task(name='academic_progress_email_task'")
    end = worker.index('\ndef _enqueue_academic_class_sync_child_job', start)
    body = worker[start:end]

    assert "acks_late=False" in body
    assert body.index('sync_class_learning_insight(') < body.index('create_bulk_session(')
    assert body.index("'mail_send_session_id': session_id") < body.index('wait_for_terminal(')
    assert "terminal_status != 'COMPLETED'" in body
    assert "'recipient_addresses_logged': False" in body


def test_progress_email_cross_layer_contract_is_wired():
    root = Path(__file__).resolve().parents[3]
    routes = (root / 'backend' / 'app' / 'api' / 'routes' / 'academic.py').read_text(encoding='utf-8')
    page = (root / 'frontend' / 'app' / 'student-management' / 'classes' / '[classId]' / 'page.tsx').read_text(encoding='utf-8')
    env_example = (root / '.env.production.example').read_text(encoding='utf-8')

    assert "'/classes/{class_id}/progress-email/preview'" in routes
    assert "'/classes/{class_id}/progress-email/jobs'" in routes
    assert 'Gửi nhắc sinh viên chậm tiến độ' in page
    assert 'masked_email' in page
    assert 'private_email' not in page
    assert 'MAILSEND_PROXY_API_KEY=' in env_example
