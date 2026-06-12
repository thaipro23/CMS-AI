from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.config import cors_origin_list, is_production
from app.core.errors import error_payload

_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _origin_value(request: Request) -> str:
    origin = request.headers.get('origin') or ''
    if origin:
        return origin.strip().rstrip('/')
    referer = request.headers.get('referer') or ''
    if not referer:
        return ''
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')


def _allowed_origins() -> set[str]:
    return {item.strip().rstrip('/') for item in cors_origin_list() if item.strip()}


def _is_allowed_origin(origin: str) -> bool:
    return origin.rstrip('/') in _allowed_origins()


def _is_cookie_authenticated_request(request: Request) -> bool:
    return bool(request.cookies.get('ai_openedx_access_token'))


async def enforce_mutating_origin_guard(request: Request):
    """Protect cookie-authenticated mutating API calls from CSRF.

    In production the AI backend accepts an HttpOnly AI session cookie. CORS alone
    does not stop CSRF, so mutating browser requests must come from the explicit
    CORS allowlist. Bearer-only server/API calls without browser cookies remain
    possible so operational scripts are not broken.
    """
    if not is_production():
        return None
    if request.method.upper() not in _MUTATING_METHODS:
        return None
    if not request.url.path.startswith('/api'):
        return None

    origin = _origin_value(request)
    if origin and not _is_allowed_origin(origin):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_payload(
                code='ORIGIN_FORBIDDEN',
                message='Mutating API request origin is not allowed.',
                status_code=status.HTTP_403_FORBIDDEN,
                request_id=request.headers.get('x-request-id'),
            ),
        )
    if _is_cookie_authenticated_request(request) and not origin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_payload(
                code='ORIGIN_REQUIRED',
                message='Origin or Referer header is required for cookie-authenticated mutating API requests.',
                status_code=status.HTTP_403_FORBIDDEN,
                request_id=request.headers.get('x-request-id'),
            ),
        )
    return None
