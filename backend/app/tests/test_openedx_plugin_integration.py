"""Opt-in integration checks for the real Open edX CMS connector plugin.

Run manually against a real Tutor/Open edX CMS with the connector installed:

    OPENEDX_INTEGRATION_TEST=1 pytest app/tests/test_openedx_plugin_integration.py -q

These tests are skipped in CI by default because they require a live CMS URL,
OAuth/HMAC secrets and a course/library available on the target environment.
"""
import os

import pytest

from app.modules.openedx_connector.real import RealOpenEdXConnector


pytestmark = pytest.mark.skipif(os.getenv('OPENEDX_INTEGRATION_TEST') != '1', reason='requires live Open edX CMS connector')


@pytest.mark.asyncio
async def test_studio_content_endpoint_returns_blocks():
    course_id = os.environ['OPENEDX_INTEGRATION_COURSE_ID']
    connector = RealOpenEdXConnector()
    blocks = await connector._get_studio_content(course_id)
    assert isinstance(blocks, list)
    assert blocks
    assert all('block_id' in block for block in blocks)


@pytest.mark.asyncio
async def test_connector_hmac_headers_are_added():
    connector = RealOpenEdXConnector()
    url = connector.cms_base_url + '/api/ai-connector/v1/diagnostics'
    headers = await connector._headers(method='GET', url=url)
    assert 'X-AI-Connector-Timestamp' in headers
    assert 'X-AI-Connector-Signature' in headers
