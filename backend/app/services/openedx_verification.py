from __future__ import annotations

import httpx
from app.core.config import settings
from app.modules.openedx_connector.factory import get_openedx_connector


async def test_openedx_connection(course_id: str | None = None) -> dict:
    """Admin smoke test for Open edX config without requiring a publish."""
    connector = get_openedx_connector()
    result: dict = {
        'ok': True,
        'use_mock_openedx': settings.use_mock_openedx,
        'base_url': settings.openedx_base_url,
        'cms_base_url': settings.openedx_cms_base_url or settings.openedx_base_url,
        'lms_base_url': settings.openedx_lms_base_url,
        'oauth_base_url': settings.openedx_oauth_base_url or settings.openedx_lms_base_url or settings.openedx_base_url,
        'course_blocks_path': settings.openedx_course_blocks_path,
        'library_endpoint': settings.openedx_library_endpoint,
        'library_import_endpoint': settings.openedx_library_import_endpoint,
        'checks': [],
    }
    try:
        if settings.use_mock_openedx:
            blocks = await connector.get_course_blocks(course_id or 'course-v1:Mock+DEMO+2026')
            result['checks'].append({'name': 'mock_course_blocks', 'ok': True, 'block_count': len(blocks)})
            return result

        # Lightweight reachability check first. Some enterprise CMS hosts return
        # HTML/Cloudflare here; that is still useful for DNS/TLS validation.
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            cms_url = (settings.openedx_cms_base_url or settings.openedx_base_url).rstrip('/')
            lms_url = (settings.openedx_lms_base_url or settings.openedx_base_url).rstrip('/')
            cms_resp = await client.get(cms_url + '/', follow_redirects=True)
            result['checks'].append({'name': 'cms_base_url_reachable', 'ok': cms_resp.status_code < 500, 'status_code': cms_resp.status_code, 'url': cms_url})
            if lms_url != cms_url:
                lms_resp = await client.get(lms_url + '/', follow_redirects=True)
                result['checks'].append({'name': 'lms_base_url_reachable', 'ok': lms_resp.status_code < 500, 'status_code': lms_resp.status_code, 'url': lms_url})

        if course_id:
            blocks = await connector.get_course_blocks(course_id)
            result['checks'].append({'name': 'course_blocks_api', 'ok': True, 'course_id': course_id, 'block_count': len(blocks)})
        return result
    except Exception as exc:
        result['ok'] = False
        result['error'] = str(exc)
        result['checks'].append({'name': 'exception', 'ok': False, 'error': str(exc)})
        return result
