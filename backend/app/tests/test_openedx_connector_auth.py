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
