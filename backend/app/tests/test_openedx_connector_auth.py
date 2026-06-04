import pytest

from app.modules.openedx_connector.real import RealOpenEdXConnector


@pytest.mark.asyncio
async def test_real_connector_uses_jwt_authorization_scheme(monkeypatch):
    connector = RealOpenEdXConnector()
    connector._access_token = None
    connector._token_type = 'JWT'

    async def fake_get_token():
        return 'header.payload.signature'

    monkeypatch.setattr(connector, '_get_token', fake_get_token)
    headers = await connector._headers()

    assert headers['Authorization'] == 'JWT header.payload.signature'
    assert headers['Accept'] == 'application/json'


@pytest.mark.asyncio
async def test_real_connector_uses_bearer_for_opaque_tokens(monkeypatch):
    connector = RealOpenEdXConnector()
    connector._access_token = None
    connector._token_type = 'Bearer'

    async def fake_get_token():
        return 'opaque-token-from-oauth-db'

    monkeypatch.setattr(connector, '_get_token', fake_get_token)
    headers = await connector._headers()

    assert headers['Authorization'] == 'Bearer opaque-token-from-oauth-db'


@pytest.mark.asyncio
async def test_real_connector_posts_create_quiz_node_to_cms(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector import real

    calls = []

    class DummyResponse:
        status_code = 200
        text = ''

        def json(self):
            return {
                'ok': True,
                'created': True,
                'created_nodes': [{'usage_key': 'block-v1:TEST+AI+2026+type@vertical+block@quiz', 'block_type': 'vertical'}],
                'leaf_unit_node_id': 'block-v1:TEST+AI+2026+type@vertical+block@quiz',
            }

    class DummyClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            calls.append({'url': url, 'content': content, 'headers': headers})
            return DummyResponse()

    monkeypatch.setattr(real.httpx, 'AsyncClient', DummyClient)
    monkeypatch.setattr(settings, 'openedx_quiz_node_create_endpoint', '/api/ai-connector/v1/courses/{course_id}/quiz-nodes')

    connector = RealOpenEdXConnector()
    connector.cms_base_url = 'http://studio.local.openedx.io'

    async def fake_get_token():
        return None

    monkeypatch.setattr(connector, '_get_token', fake_get_token)
    monkeypatch.setattr(connector, '_hmac_headers', lambda method, url, body: {'X-AI-Connector-Signature': 'test-signature'})

    result = await connector.create_quiz_node(
        'course-v1:TEST+AI+2026',
        'block-v1:TEST+AI+2026+type@chapter+block@chapter-1',
        'AI Learning Check - Chương 1',
        'Quiz tự luyện',
        {'family_bank_slots': []},
    )

    assert result['ok'] is True
    assert calls[0]['url'] == 'http://studio.local.openedx.io/api/ai-connector/v1/courses/course-v1:TEST+AI+2026/quiz-nodes'
    assert calls[0]['headers']['X-AI-Connector-Signature'] == 'test-signature'
    assert b'parent_node_id' in calls[0]['content']
    assert b'AI Learning Check' in calls[0]['content']


@pytest.mark.asyncio
async def test_real_connector_posts_insert_problem_banks_to_cms(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector import real

    calls = []

    class DummyResponse:
        status_code = 200
        text = ''

        def json(self):
            return {
                'ok': True,
                'created': True,
                'problem_bank_blocks': [
                    {
                        'usage_key': 'block-v1:TEST+AI+2026+type@library_content+block@slot-01',
                        'block_type': 'library_content',
                        'selection_verified': False,
                    }
                ],
                'manual_component_selection_required': True,
            }

    class DummyClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            calls.append({'url': url, 'content': content, 'headers': headers})
            return DummyResponse()

    monkeypatch.setattr(real.httpx, 'AsyncClient', DummyClient)
    monkeypatch.setattr(settings, 'openedx_problem_bank_insert_endpoint', '/api/ai-connector/v1/courses/{course_id}/problem-banks')

    connector = RealOpenEdXConnector()
    connector.cms_base_url = 'http://studio.local.openedx.io'

    async def fake_get_token():
        return None

    monkeypatch.setattr(connector, '_get_token', fake_get_token)
    monkeypatch.setattr(connector, '_hmac_headers', lambda method, url, body: {'X-AI-Connector-Signature': 'test-signature'})

    result = await connector.insert_problem_banks(
        'course-v1:TEST+AI+2026',
        'block-v1:TEST+AI+2026+type@vertical+block@quiz',
        [{'slot_no': 1, 'library_key': 'lib:FPT:test', 'openedx_problem_ids': ['lb:FPT:test:problem:p1']}],
        {'family_bank_plan': {'slots': []}},
    )

    assert result['ok'] is True
    assert calls[0]['url'] == 'http://studio.local.openedx.io/api/ai-connector/v1/courses/course-v1:TEST+AI+2026/problem-banks'
    assert calls[0]['headers']['X-AI-Connector-Signature'] == 'test-signature'
    assert b'unit_node_id' in calls[0]['content']
    assert b'openedx_problem_ids' in calls[0]['content']
