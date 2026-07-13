from __future__ import annotations

from fastapi import Response

from app.core.config import is_production, settings


_DEFAULT_PERMISSIONS_POLICY = (
    'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), '
    'microphone=(), payment=(), usb=(), interest-cohort=()'
)


def apply_security_headers(response: Response) -> None:
    """Apply conservative browser security headers to every backend response.

    The AI backend is mostly JSON/API, but it still participates in browser SSO,
    cookie-authenticated flows, exports, and operational dashboards. These
    headers reduce the blast radius of common attacks without changing API
    response bodies or requiring a database migration.
    """
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    response.headers.setdefault('Permissions-Policy', _DEFAULT_PERMISSIONS_POLICY)
    response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-site')
    response.headers.setdefault('Cache-Control', 'no-store')
    response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
    # Keep CSP conservative for API responses. Frontend CSP should be managed by
    # the Next.js host/reverse proxy because it serves scripts/styles/assets.
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    if is_production() and bool(getattr(settings, 'auth_cookie_secure', True)):
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
