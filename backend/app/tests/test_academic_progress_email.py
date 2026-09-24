from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicBulkOperationJob
from app.services.academic import progress_email as progress_email_module
from app.services.academic.progress_email import mask_recipient_email, plain_text_mail_template
from app.services.academic.progress_email_delivery import (
    build_delivery_intent,
    delivery_reconciliation_action,
    recipient_matches_intent,
)
from app.services.mailsend_proxy import MailSendProxyClient, MailSendProxyError
from app import worker as worker_module


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
            assert b'name="payload"' in content
            assert b'Content-Type: application/json' in content
            assert b'name="subject"' not in content
            assert b'name="bodyTemplate"' not in content
            assert b'name="sourceTo.inlineEmails"' not in content
            assert b'"deliveryMode": "perRecipient"' in content
            assert b'"isAnonymous": false' in content
            assert b'"isHtml": true' in content
            assert b'"inlineEmails": ["sv001@example.edu.vn", "sv002@example.edu.vn"]' in content
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
            idempotency_key='progress-email:job-1:student-1',
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
    assert requests[0].headers['Idempotency-Key'] == 'progress-email:job-1:student-1'


def test_mail_send_proxy_accepts_idempotent_replay_response():
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers['Idempotency-Key'])
        return httpx.Response(200, json={'sessionId': 'existing-session', 'status': 'QUEUED'})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = MailSendProxyClient(
            base_url='https://mailsend.example.test',
            api_key='proxy-secret',
            http_client=http_client,
        )
        result = client.create_bulk_session(
            subject='Nhắc tiến độ',
            body_template='<p>Nội dung</p>',
            emails=['student@example.edu.vn'],
            idempotency_key='progress-email:job-1:student-1',
        )

    assert result['session_id'] == 'existing-session'
    assert seen_keys == ['progress-email:job-1:student-1']


def test_worker_loss_after_provider_acceptance_replays_same_intent_not_new_delivery(monkeypatch):
    monkeypatch.setattr(progress_email_module.settings, 'jwt_secret', 'test-secret-that-is-long-enough-for-hmac')
    intent = build_delivery_intent(
        job_id='job-lost-after-accept',
        recipient={
            'student_id': 'student-1',
            'private_email': 'student01@fpt.edu.vn',
        },
    )
    accepted_keys: dict[str, str] = {}
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers['Idempotency-Key']
        calls.append(key)
        session_id = accepted_keys.setdefault(key, 'session-once')
        return httpx.Response(202 if len(calls) == 1 else 200, json={
            'sessionId': session_id,
            'status': 'QUEUED',
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = MailSendProxyClient(
            base_url='https://mailsend.example.test',
            api_key='proxy-secret',
            http_client=http_client,
        )
        first = client.create_bulk_session(
            subject='Nhắc tiến độ',
            body_template='<p>Nội dung</p>',
            emails=['student01@fpt.edu.vn'],
            idempotency_key=intent['idempotency_key'],
        )
        # Simulate a worker disappearing before it can persist first.session_id.
        replay = client.create_bulk_session(
            subject='Nhắc tiến độ',
            body_template='<p>Nội dung</p>',
            emails=['student01@fpt.edu.vn'],
            idempotency_key=intent['idempotency_key'],
        )

    assert first['session_id'] == replay['session_id'] == 'session-once'
    assert calls == [intent['idempotency_key'], intent['idempotency_key']]
    assert len(accepted_keys) == 1


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
                idempotency_key='progress-email:job-1:student-private',
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
    linked = plain_text_mail_template('Vui lòng vào CMS để kiểm tra')
    assert 'https://edx.cms.fpl.edu.vn/learner-dashboard/' in linked
    assert '>CMS</a>' in linked


def test_progress_email_delivery_intent_is_stable_private_and_reconcilable(monkeypatch):
    monkeypatch.setattr(progress_email_module.settings, 'jwt_secret', 'test-secret-that-is-long-enough-for-hmac')
    recipient = {
        'student_id': 'student-1',
        'student_code': 'PH12345',
        'full_name': 'Nguyễn Văn An',
        'private_email': 'Student01@fpt.edu.vn',
    }

    first = build_delivery_intent(job_id='job-1', recipient=recipient)
    second = build_delivery_intent(job_id='job-1', recipient=recipient)

    assert first == second
    assert first['provider_state'] == 'intent_created'
    assert first['idempotency_key'].startswith('progress-email:v1:')
    assert recipient['private_email'].lower() not in str(first).lower()
    assert recipient_matches_intent(first, 'student01@fpt.edu.vn') is True
    assert recipient_matches_intent(first, 'changed@fpt.edu.vn') is False
    assert delivery_reconciliation_action(first) == 'create_idempotently'
    assert delivery_reconciliation_action({**first, 'provider_state': 'provider_unknown'}) == 'create_idempotently'
    assert delivery_reconciliation_action({**first, 'provider_state': 'provider_created', 'session_id': 's-1'}) == 'poll'
    assert delivery_reconciliation_action({**first, 'provider_state': 'terminal'}) == 'done'


def test_ai_server_resolves_student_name_and_code_before_mail_send():
    render = getattr(progress_email_module, 'render_recipient_body_text', None)
    assert callable(render), 'AI Server must own progress-email recipient personalization'

    body = render(
        'Xin chào {{tên sinh viên}}-{{maHs}},\nVui lòng vào CMS để kiểm tra.',
        full_name='Nguyễn Văn An',
        student_code='PH12345',
    )
    assert body.startswith('Xin chào Nguyễn Văn An-PH12345,')
    assert '{{tên sinh viên}}' not in body
    assert '{{maHs}}' not in body

    with pytest.raises(ValueError, match='student_code'):
        render('Xin chào {{maHs}}', full_name='Nguyễn Văn An', student_code=None)


def test_worker_refreshes_cms_before_creating_mail_send_session():
    root = Path(__file__).resolve().parents[1]
    worker = (root / 'worker.py').read_text(encoding='utf-8')
    start = worker.index("@celery_app.task(name='academic_progress_email_task'")
    end = worker.index('\ndef _enqueue_academic_class_sync_child_job', start)
    body = worker[start:end]

    assert "acks_late=False" in body
    assert body.index('sync_class_learning_insight(') < body.index('create_bulk_session(')
    assert "resolved.pop('recipients')" in body
    assert 'render_recipient_body_text(' in body
    assert 'emails=[recipient_email]' in body
    assert "'mail_send_deliveries'" in body
    assert "'recipient_addresses_logged': False" in body
    assert body.index("'provider_state': 'intent_created'") < body.index('create_bulk_session(')
    assert 'idempotency_key=state[\'idempotency_key\']' in body
    assert "'provider_state': 'provider_unknown'" in body
    assert "'provider_state': 'provider_created'" in body
    assert "delivery_reconciliation_action(state)" in body


def test_progress_email_watchdog_is_scheduled_for_durable_reconciliation():
    root = Path(__file__).resolve().parents[1]
    worker = (root / 'worker.py').read_text(encoding='utf-8')

    assert "'academic_progress_email_watchdog_task': {'queue': 'exports'}" in worker
    assert "'task': 'academic_progress_email_watchdog_task'" in worker
    assert "job_type == 'progress_reminder_email'" in worker


def test_progress_email_watchdog_requeues_unknown_provider_state(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicBulkOperationJob.__table__.create(engine)
    old = datetime.utcnow() - timedelta(hours=1)
    with Session(engine) as db:
        db.add(AcademicBulkOperationJob(
            id='progress-job-1',
            job_type='progress_reminder_email',
            status='running',
            updated_at=old,
            result_json={
                'mail_send_deliveries': [{
                    'student_id': 'student-1',
                    'provider_state': 'provider_unknown',
                    'idempotency_key': 'progress-email:v1:key',
                }],
            },
        ))
        db.commit()

    calls: list[dict] = []
    monkeypatch.setattr(worker_module, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(worker_module.settings, 'mailsend_poll_timeout_seconds', 1)
    monkeypatch.setattr(worker_module.settings, 'mailsend_request_timeout_seconds', 1)
    monkeypatch.setattr(
        worker_module.academic_progress_email_task,
        'apply_async',
        lambda **kwargs: calls.append(kwargs),
    )

    result = worker_module.academic_progress_email_watchdog_task.run()

    assert result == {'ok': True, 'requeued': 1}
    assert calls == [{
        'args': ['progress-job-1'],
        'queue': 'exports',
        'task_id': 'academic-progress-email-reconcile:progress-job-1:1',
    }]
    with Session(engine) as db:
        job = db.get(AcademicBulkOperationJob, 'progress-job-1')
        assert job.status == 'queued'
        assert job.result_json['reconciliation_attempt'] == 1
    engine.dispose()


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
