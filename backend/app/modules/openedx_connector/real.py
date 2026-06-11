import hashlib
import hmac
import ipaddress
import json
import re
import socket
import time
from html import unescape
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from app.core.config import settings
from app.modules.openedx_connector.base import OpenEdXConnector




def _clean_openedx_usage_key(value: object) -> str:
    """Normalize usage keys saved from older connector responses.

    Some rollback rows can contain JSON-encoded strings such as
    '"lb:FPT:..."'.  Sending those quotes to Open edX makes the CMS
    connector fail parsing the LibraryUsageLocatorV2.
    """
    import json
    from urllib.parse import unquote

    text = str(value or '').strip()
    # Decode URL-encoded values, then unwrap JSON/string quotes a few times.
    for _ in range(3):
        decoded = unquote(text).strip()
        if decoded != text:
            text = decoded
            continue
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            inner = text[1:-1].strip()
            if inner != text:
                text = inner
                continue
        try:
            loaded = json.loads(text)
            if isinstance(loaded, str) and loaded != text:
                text = loaded.strip()
                continue
        except Exception:
            pass
        break
    return text

class RealOpenEdXConnector(OpenEdXConnector):
    """CMS API connector.

    This connector normalizes CMS/Open edX responses into a small internal block
    shape so the rest of AI Server does not depend on a specific Tutor/Open edX
    release.

    Local CMS notes:
    - /oauth2/access_token/ can return token_type="JWT" when token_type=jwt is
      requested.
    - JWT tokens must be sent as ``Authorization: JWT <token>`` in many CMS APIs.
      Sending them as ``Bearer`` can trigger ``token_nonexistent`` because the
      server tries to look up an opaque OAuth token in the database.
    - Course Blocks API may return only transcript URLs for video blocks. This
      connector downloads those transcript URLs and exposes transcript text as
      normal content so the chunking/generation pipeline can use real learning
      content, not just course structure.
    """

    def __init__(self):
        # CMS/Studio hosts the AI connector endpoints used for draft-content sync and publish.
        self.cms_base_url = (settings.openedx_cms_base_url or settings.openedx_base_url).rstrip('/')
        # LMS usually hosts OAuth2 token and learner-facing Course Blocks APIs in Tutor/Open edX.
        self.lms_base_url = (settings.openedx_lms_base_url or settings.openedx_base_url).rstrip('/')
        self.oauth_base_url = (settings.openedx_oauth_base_url or settings.openedx_lms_base_url or settings.openedx_base_url).rstrip('/')
        # Keep base_url as CMS alias for old helper code.
        self.base_url = self.cms_base_url
        self._access_token: str | None = settings.openedx_access_token
        self._token_type: str | None = self._infer_token_type(settings.openedx_access_token)

    def _trusted_download_hosts(self) -> set[str]:
        hosts: set[str] = set()
        for base in (self.cms_base_url, self.lms_base_url, self.oauth_base_url):
            try:
                host = urlparse(base).hostname
                if host:
                    hosts.add(host.lower())
            except Exception:
                pass
        for host in (settings.openedx_allowed_download_hosts or '').split(','):
            clean = host.strip().lower()
            if clean:
                hosts.add(clean)
        return hosts

    @staticmethod
    def _host_resolves_to_private_address(hostname: str) -> bool:
        try:
            ipaddress.ip_address(hostname)
            addresses = [hostname]
        except ValueError:
            try:
                addresses = [item[4][0] for item in socket.getaddrinfo(hostname, None)]
            except socket.gaierror:
                return True
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                return True
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return True
        return False

    def _assert_safe_download_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise RuntimeError('Blocked unsafe asset/transcript URL: invalid scheme or host')
        host = parsed.hostname.lower()
        trusted_hosts = self._trusted_download_hosts()
        if host in trusted_hosts:
            return
        if self._host_resolves_to_private_address(host):
            raise RuntimeError(f'Blocked unsafe asset/transcript URL host: {host}')
        raise RuntimeError(f'Blocked asset/transcript URL host not in OPENEDX_ALLOWED_DOWNLOAD_HOSTS: {host}')

    @staticmethod
    def _signature_path(url: str) -> str:
        parsed = urlparse(url)
        return parsed.path + (f'?{parsed.query}' if parsed.query else '')

    def _hmac_headers(self, method: str, url: str, body: bytes = b'') -> dict[str, str]:
        secret = settings.openedx_connector_hmac_secret
        if not secret:
            return {}
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body or b'').hexdigest()
        message = f'{timestamp}.{method.upper()}.{self._signature_path(url)}.{body_hash}'
        signature = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        return {
            'X-AI-Connector-Timestamp': timestamp,
            'X-AI-Connector-Signature': signature,
        }

    @staticmethod
    def _json_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    async def _json_request_headers(self, method: str, url: str, body: bytes) -> dict[str, str]:
        headers = await self._headers(method=method, url=url, body=body)
        headers['Content-Type'] = 'application/json'
        return headers

    async def _read_limited_bytes(self, client: httpx.AsyncClient, url: str, headers: dict[str, str], max_bytes: int) -> tuple[bytes, str]:
        self._assert_safe_download_url(url)
        data = bytearray()
        async with client.stream('GET', url, headers=headers) as response:
            response.raise_for_status()
            content_length = response.headers.get('content-length')
            if content_length:
                try:
                    declared_size = int(content_length)
                except (TypeError, ValueError):
                    declared_size = 0
                if declared_size > max_bytes:
                    raise RuntimeError(f'Download exceeded safe size limit from Content-Length: {max_bytes} bytes')
            content_type = response.headers.get('content-type', '')
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise RuntimeError(f'Download exceeded safe size limit: {max_bytes} bytes')
        return bytes(data), content_type

    @staticmethod
    def _infer_token_type(token: str | None) -> str | None:
        """Infer auth scheme for a manually supplied token."""
        if not token:
            return None
        return 'JWT' if token.count('.') == 2 else 'Bearer'

    @staticmethod
    def _normalize_auth_scheme(token_type: str | None) -> str:
        """Convert OAuth token_type into the Authorization header scheme."""
        value = (token_type or 'Bearer').strip()
        if value.lower() == 'jwt':
            return 'JWT'
        if value.lower() == 'bearer':
            return 'Bearer'
        return value

    async def _get_token(self) -> str | None:
        if self._access_token:
            return self._access_token
        if not settings.openedx_client_id or not settings.openedx_client_secret:
            return None

        token_url = f'{self.oauth_base_url}{settings.openedx_oauth_token_url}'
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(
                token_url,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': settings.openedx_client_id,
                    'client_secret': settings.openedx_client_secret,
                    # Tutor/Open edX can issue JWT access tokens for server-to-server calls.
                    'token_type': 'jwt',
                    'scope': 'read write',
                },
            )
            response.raise_for_status()
            payload = response.json()
            self._access_token = payload.get('access_token')
            self._token_type = payload.get('token_type') or self._infer_token_type(self._access_token) or 'Bearer'
            return self._access_token

    async def _headers(self, method: str = 'GET', url: str = '', body: bytes = b'') -> dict[str, str]:
        token = await self._get_token()
        headers = {'Accept': 'application/json'}
        if token:
            scheme = self._normalize_auth_scheme(self._token_type)
            headers['Authorization'] = f'{scheme} {token}'
        if url:
            headers.update(self._hmac_headers(method, url, body))
        return headers


    @staticmethod
    def _raise_for_openedx_error(response: httpx.Response, step: str) -> None:
        """Raise an actionable error that includes the connector JSON body.

        httpx.raise_for_status() hides the useful JSON detail from the CMS
        connector. Publish troubleshooting needs that body because Open edX can
        fail due to missing Libraries V2, missing staff user, invalid OLX, etc.
        """
        if response.status_code < 400:
            return
        detail: str
        try:
            payload = response.json()
            detail = json.dumps(payload, ensure_ascii=False)
        except Exception:
            detail = response.text[:2000]
        raise RuntimeError(f'Open edX connector {step} failed HTTP {response.status_code}: {detail}')

    async def get_course_blocks(self, course_id: str) -> list[dict]:
        """Load course content for AI sync.

        Preferred path: the Studio connector plugin installed inside CMS.  It can
        read draft modulestore content, old problem XML and linked assets.
        Fallback path: learner-facing Course Blocks API.
        """
        if settings.openedx_prefer_studio_content and settings.openedx_studio_content_endpoint:
            try:
                studio_blocks = await self._get_studio_content(course_id)
                if studio_blocks:
                    return studio_blocks
            except Exception:
                # Keep fallback so a missing/not-yet-installed plugin does not break local sync.
                pass

        return await self._get_course_blocks_api(course_id)

    async def _get_studio_content(self, course_id: str) -> list[dict]:
        endpoint = settings.openedx_studio_content_endpoint.format(course_id=course_id)
        url = f'{self.cms_base_url}{endpoint}'
        params = {
            'include_drafts': 'true',
            'include_assets': 'true',
            'include_problems': 'true',
        }
        signed_url = f'{url}?{urlencode(params)}'
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.get(url, params=params, headers=await self._headers(method='GET', url=signed_url))
            response.raise_for_status()
            payload = response.json()

        blocks = payload.get('blocks') or []
        normalized: list[dict] = []
        if isinstance(blocks, dict):
            iterable = blocks.items()
        else:
            iterable = [(item.get('block_id') or item.get('id'), item) for item in blocks if isinstance(item, dict)]
        for block_id, block in iterable:
            normalized.append(await self._normalize_block(block_id, block))
        return normalized

    async def _get_course_blocks_api(self, course_id: str) -> list[dict]:
        # Use repeated student_view_data parameters. A dict would collapse duplicate
        # keys and CMS would not return html/video student view data consistently.
        params = [
            ('course_id', course_id),
            ('all_blocks', 'true'),
            ('depth', 'all'),
            ('requested_fields', 'children,display_name,type,data,student_view_data,metadata,lms_web_url,student_view_url'),
            ('student_view_data', 'html'),
            ('student_view_data', 'video'),
            ('student_view_data', 'problem'),
        ]
        url = f'{self.lms_base_url}{settings.openedx_course_blocks_path}'
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.get(url, params=params, headers=await self._headers(method='GET', url=url))
            response.raise_for_status()
            payload = response.json()

        blocks = payload.get('blocks') or payload.get('root') or {}
        if isinstance(blocks, dict):
            normalized = []
            for block_id, block in blocks.items():
                normalized.append(await self._normalize_block(block_id, block))
            return normalized
        if isinstance(blocks, list):
            normalized = []
            for item in blocks:
                normalized.append(await self._normalize_block(item.get('id') or item.get('block_id'), item))
            return normalized
        return []

    async def _download_text(self, url: str) -> str:
        """Download a transcript/text URL and normalize common CMS transcript shapes."""
        if not url:
            return ''

        headers = {'Accept': 'application/json,text/plain,text/vtt,text/srt,*/*'}
        # Local noauth transcript URLs usually work without auth. If the URL points
        # back to the configured CMS host, attach auth headers as a fallback for
        # deployments that protect transcript endpoints.
        try:
            parsed = urlparse(url)
            base = urlparse(self.cms_base_url)
            if parsed.netloc == base.netloc:
                headers.update(await self._headers())
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds, follow_redirects=False) as client:
            raw, content_type = await self._read_limited_bytes(client, url, headers, settings.openedx_transcript_max_bytes)
            content_type = content_type.lower()
            text = raw.decode('utf-8', errors='replace')

        if 'json' in content_type:
            try:
                return self._transcript_json_to_text(json.loads(text))
            except Exception:
                return self._clean_transcript_text(text)

        # Some transcript endpoints return JSON without a JSON content type.
        stripped = text.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                return self._transcript_json_to_text(json.loads(stripped))
            except Exception:
                pass

        return self._clean_transcript_text(text)

    def _transcript_json_to_text(self, value: Any) -> str:
        """Extract readable transcript text from sjson/list/dict transcript payloads."""
        pieces: list[str] = []

        def walk(item: Any):
            if item is None:
                return
            if isinstance(item, str):
                cleaned = self._clean_transcript_text(item)
                if cleaned:
                    pieces.append(cleaned)
                return
            if isinstance(item, list):
                for child in item:
                    walk(child)
                return
            if isinstance(item, dict):
                for key in ('text', 'content', 'transcript', 'caption', 'value'):
                    if key in item:
                        walk(item.get(key))
                        return
                for key in ('lines', 'paragraphs', 'segments', 'subtitles', 'captions'):
                    if key in item:
                        walk(item.get(key))
                        return
                # Open edX .sjson often uses arrays such as {"text": [...]} but
                # if the shape is different, traverse non-timing fields only.
                for key, child in item.items():
                    if str(key).lower() in {'start', 'end', 'duration', 'id', 'time', 'timestamp'}:
                        continue
                    walk(child)

        walk(value)
        return self._normalize_plain_text(' '.join(pieces))

    def _clean_transcript_text(self, text: str) -> str:
        text = text or ''
        # WebVTT/SRT cleanup.
        text = re.sub(r'^WEBVTT.*?\n', ' ', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'\d{1,6}\s*\n', ' ', text)
        text = re.sub(r'\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}[^\n]*', ' ', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        return self._normalize_plain_text(text)

    def _clean_html_text(self, text: str) -> str:
        text = text or ''
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        return self._normalize_plain_text(text)

    @staticmethod
    def _normalize_plain_text(text: str) -> str:
        return re.sub(r'\s+', ' ', unescape(text or '')).strip()

    def _student_view_html_text(self, student_data: Any) -> str:
        if not isinstance(student_data, dict):
            return ''
        # CMS returns {enabled: false, message: ...} when HTML student view data is disabled.
        # Do not convert that warning message into a learning chunk.
        if student_data.get('enabled') is False and 'ENABLE_HTML_XBLOCK_STUDENT_VIEW_DATA' in str(student_data.get('message', '')):
            return ''
        for key in ('html', 'content', 'data', 'body', 'text'):
            value = student_data.get(key)
            if isinstance(value, str) and value.strip():
                return self._clean_html_text(value)
            if isinstance(value, dict):
                nested = self._student_view_html_text(value)
                if nested:
                    return nested
        return ''


    async def _download_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Download linked CMS assets when possible so ContentExtractor can parse PDF/PPTX/TXT.

        The Studio connector returns asset URLs.  CourseSyncService runs outside
        CMS, so this connector downloads the bytes in memory and attaches them to
        the normalized block.  If download fails, keep the URL metadata so the
        UI/debug log still shows the attachment source.
        """
        url = asset.get('url') or asset.get('source_ref') or asset.get('asset_id')
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            return asset

        headers = {'Accept': '*/*'}
        try:
            parsed = urlparse(url)
            base = urlparse(self.cms_base_url)
            if parsed.netloc == base.netloc:
                headers.update(await self._headers())
        except Exception:
            pass

        try:
            async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds, follow_redirects=False) as client:
                data, content_type = await self._read_limited_bytes(client, url, headers, settings.openedx_asset_max_bytes)
        except Exception:
            return asset

        filename = asset.get('filename') or asset.get('file_name') or url.rstrip('/').split('/')[-1] or 'asset'
        return {
            **asset,
            'asset_id': asset.get('asset_id') or url,
            'url': url,
            'filename': filename,
            'file_name': filename,
            'display_name': asset.get('display_name') or filename,
            'mime_type': asset.get('mime_type') or content_type,
            'content_type': asset.get('content_type') or content_type,
            'bytes': data,
            'source_ref': asset.get('source_ref') or url,
        }

    async def _normalize_assets(self, block: dict[str, Any]) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw_assets = block.get('assets') or []
        if isinstance(raw_assets, dict):
            raw_assets = list(raw_assets.values())
        if not isinstance(raw_assets, list):
            raw_assets = [raw_assets]

        for item in raw_assets:
            if not isinstance(item, dict):
                item = {'url': str(item), 'asset_id': str(item)}
            key = str(item.get('url') or item.get('source_ref') or item.get('asset_id') or item.get('filename') or '')
            if not key or key in seen:
                continue
            seen.add(key)
            assets.append(await self._download_asset(item))
        return assets

    async def _normalize_block(self, block_id: str | None, block: dict) -> dict:
        metadata = block.get('metadata') or {}
        student_data = block.get('student_view_data') or {}
        block_type = (block.get('type') or block.get('block_type') or 'unknown').lower()
        raw_data = block.get('problem_xml') or block.get('data') or ''

        assets = await self._normalize_assets(block)

        transcripts = []
        transcript_payload = student_data.get('transcripts') if isinstance(student_data, dict) else None
        if isinstance(transcript_payload, dict):
            for lang, value in transcript_payload.items():
                transcript_text = ''
                source_ref = f'{block_id}:transcript:{lang}'
                if isinstance(value, str) and value.startswith(('http://', 'https://')):
                    source_ref = value
                    try:
                        transcript_text = await self._download_text(value)
                    except Exception:
                        transcript_text = ''
                else:
                    transcript_text = self._clean_transcript_text(str(value or ''))

                if transcript_text.strip():
                    transcripts.append({
                        'block_id': f'{block_id}:transcript:{lang}',
                        'display_name': f'Transcript {lang}',
                        'content': transcript_text,
                        'source_ref': source_ref,
                    })

        if block_type == 'html':
            data = self._student_view_html_text(student_data)
            if not data and isinstance(raw_data, str):
                data = self._clean_html_text(raw_data)
        elif block_type == 'problem':
            # Keep raw OLX/XML for ContentExtractor so correct="true" answers are preserved.
            if isinstance(raw_data, dict):
                data = raw_data.get('problem_xml') or raw_data.get('xml') or raw_data.get('data') or ''
            else:
                data = str(raw_data or '')
        elif block_type == 'video':
            # Keep transcript entries in `transcripts`; ContentExtractor will create
            # one transcript chunk per language. Do not also put the same text in
            # `data`, otherwise sync would create duplicate video+transcript chunks.
            data = ''
        elif isinstance(raw_data, dict):
            data = '\n'.join(f'{key}: {value}' for key, value in raw_data.items() if value)
        else:
            data = str(raw_data or '')

        return {
            'block_id': block_id or block.get('id') or '',
            'type': block.get('type') or block.get('block_type') or 'unknown',
            'display_name': block.get('display_name') or block.get('name') or '',
            'data': str(data or ''),
            'parent_block_id': block.get('parent') or block.get('parent_block_id'),
            'children': block.get('children') or [],
            'metadata': metadata,
            'source_ref': block.get('lms_web_url') or block.get('student_view_url') or block_id or '',
            'transcripts': transcripts,
            'assets': assets,
        }

    async def ensure_problem_library(self, course_id: str, chapter_node_id: str, display_name: str, metadata: dict | None = None) -> dict:
        url = f'{self.cms_base_url}{settings.openedx_library_endpoint.format(course_id=course_id)}'
        metadata = metadata or {}
        payload = {
            'chapter_node_id': chapter_node_id,
            'display_name': display_name,
            'library_key': metadata.get('library_key'),
            'tag_names': metadata.get('tag_names') or metadata.get('tags') or [],
            'metadata': metadata,
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'ensure_library')
            return response.json()

    async def import_problem_to_library(self, course_id: str, library_key: str, olx: str, display_name: str, metadata: dict | None = None) -> dict:
        url = f'{self.cms_base_url}{settings.openedx_library_import_endpoint.format(course_id=course_id, library_key=library_key)}'
        metadata = metadata or {}
        payload = {
            'course_id': course_id,
            'library_key': library_key,
            'display_name': display_name,
            'olx': olx,
            'tag_names': metadata.get('tag_names') or metadata.get('tags') or [],
            'metadata': metadata,
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'import_problem')
            return response.json()


    async def verify_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict | None = None) -> dict:
        endpoint = getattr(settings, 'openedx_library_verify_endpoint', '/api/ai-connector/v1/libraries/{library_key}/problems/verify')
        url = f'{self.cms_base_url}{endpoint.format(course_id=course_id, library_key=library_key)}'
        clean_problem_id = _clean_openedx_usage_key(problem_id)
        payload = {'course_id': course_id, 'library_key': library_key, 'problem_id': clean_problem_id, 'metadata': metadata or {}}
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'verify_problem')
            return response.json()

    async def delete_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict | None = None) -> dict:
        endpoint = getattr(settings, 'openedx_library_delete_endpoint', '/api/ai-connector/v1/libraries/{library_key}/problems/delete')
        url = f'{self.cms_base_url}{endpoint.format(course_id=course_id, library_key=library_key)}'
        clean_problem_id = _clean_openedx_usage_key(problem_id)
        payload = {'course_id': course_id, 'library_key': library_key, 'problem_id': clean_problem_id, 'metadata': metadata or {}}
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'delete_problem')
            return response.json()

    async def create_quiz_node(
        self,
        course_id: str,
        parent_node_id: str,
        quiz_title: str,
        unit_title: str,
        metadata: dict | None = None,
    ) -> dict:
        endpoint = getattr(settings, 'openedx_quiz_node_create_endpoint', '/api/ai-connector/v1/courses/{course_id}/quiz-nodes')
        url = f'{self.cms_base_url}{endpoint.format(course_id=course_id)}'
        payload = {
            'course_id': course_id,
            'parent_node_id': _clean_openedx_usage_key(parent_node_id),
            'quiz_title': quiz_title,
            'unit_title': unit_title,
            'metadata': metadata or {},
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'create_quiz_node')
            return response.json()

    async def delete_quiz_node(
        self,
        course_id: str,
        node_id: str,
        metadata: dict | None = None,
    ) -> dict:
        endpoint = getattr(settings, 'openedx_quiz_node_delete_endpoint', '/api/ai-connector/v1/courses/{course_id}/quiz-nodes/delete')
        url = f'{self.cms_base_url}{endpoint.format(course_id=course_id)}'
        payload = {
            'course_id': course_id,
            'node_id': _clean_openedx_usage_key(node_id),
            'metadata': metadata or {},
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'delete_quiz_node')
            return response.json()

    async def upsert_quiz_timer_config(
        self,
        *,
        course_id: str,
        sequence_usage_key: str,
        unit_usage_key: str,
        title: str,
        duration_seconds: int,
        cooldown_seconds: int,
        enabled: bool = True,
        auto_submit_on_timeout: bool = True,
        lock_after_timeout: bool = True,
        native_timed_exam: bool = False,
        metadata: dict | None = None,
    ) -> dict:
        endpoint = getattr(settings, 'openedx_quiz_timer_config_upsert_endpoint', '/api/unit-reset/v1/quiz-config/upsert')
        # Timer sessions are enforced in LMS, so write config through LMS rather than CMS.
        url = f'{self.lms_base_url}{endpoint.format(course_id=course_id)}'
        payload = {
            'course_id': course_id,
            'sequence_usage_key': _clean_openedx_usage_key(sequence_usage_key),
            'unit_usage_key': _clean_openedx_usage_key(unit_usage_key),
            'title': title or 'Quiz',
            'duration_seconds': int(duration_seconds or 0),
            'cooldown_seconds': int(cooldown_seconds or 0),
            'enabled': bool(enabled),
            'auto_submit_on_timeout': bool(auto_submit_on_timeout),
            'lock_after_timeout': bool(lock_after_timeout),
            'native_timed_exam': bool(native_timed_exam),
            'metadata': metadata or {},
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'upsert_quiz_timer_config')
            return response.json()

    async def insert_problem_banks(
        self,
        course_id: str,
        unit_node_id: str,
        slots: list[dict[str, Any]],
        metadata: dict | None = None,
    ) -> dict:
        endpoint = getattr(settings, 'openedx_problem_bank_insert_endpoint', '/api/ai-connector/v1/courses/{course_id}/problem-banks')
        url = f'{self.cms_base_url}{endpoint.format(course_id=course_id)}'
        payload = {
            'course_id': course_id,
            'unit_node_id': _clean_openedx_usage_key(unit_node_id),
            'slots': slots or [],
            'metadata': metadata or {},
        }
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'insert_problem_banks')
            return response.json()

    async def publish_problem_olx(self, course_id: str, parent_block_id: str | None, olx: str, display_name: str) -> dict:
        url = f'{self.cms_base_url}{settings.openedx_publish_endpoint.format(course_id=course_id)}'
        payload = {'parent_block_id': parent_block_id, 'display_name': display_name, 'olx': olx}
        body = self._json_body(payload)
        async with httpx.AsyncClient(timeout=settings.openedx_request_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=await self._json_request_headers('POST', url, body))
            self._raise_for_openedx_error(response, 'publish_problem')
            return response.json()
