from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.3'
ORIGIN = 'http://ai.cms-test.poly.edu.vn'


def _main_source() -> str:
    return (ROOT / 'backend/app/main.py').read_text(encoding='utf-8')


def _cors_headers_from_source() -> list[str]:
    tree = ast.parse(_main_source())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == '_base_cors_headers' for target in node.targets):
                value = ast.literal_eval(node.value)
                assert isinstance(value, list)
                return value
    raise AssertionError('_base_cors_headers assignment not found')


def test_version_is_synchronized_in_active_runtime_files():
    targets = [
        ROOT / 'backend/app/core/config.py',
        ROOT / 'frontend/package.json',
        ROOT / 'frontend/package-lock.json',
        ROOT / 'e2e/package.json',
        ROOT / 'e2e/package-lock.json',
        ROOT / 'frontend/Dockerfile',
        ROOT / 'docker-compose.prod.yml',
        ROOT / '.env.production.example',
        ROOT / '.env.uat-http.example',
        ROOT / '.github/workflows/ci.yml',
    ]
    assert all(VERSION in path.read_text(encoding='utf-8') for path in targets)


def test_request_id_is_allowed_and_exposed_by_cors_contract():
    source = _main_source()
    headers = _cors_headers_from_source()
    assert 'X-Request-ID' in headers
    assert "expose_headers=['X-Request-ID', 'X-Process-Time-Ms']" in source


def test_exchange_preflight_accepts_request_id_header():
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ORIGIN],
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
        allow_headers=_cors_headers_from_source(),
        expose_headers=['X-Request-ID', 'X-Process-Time-Ms'],
    )

    @app.post('/api/auth/openedx-session/exchange')
    def exchange() -> dict[str, bool]:
        return {'ok': True}

    response = TestClient(app).options(
        '/api/auth/openedx-session/exchange',
        headers={
            'Origin': ORIGIN,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-request-id',
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers['access-control-allow-origin'] == ORIGIN
    assert response.headers['access-control-allow-credentials'] == 'true'
    allowed = response.headers['access-control-allow-headers'].lower()
    assert 'content-type' in allowed
    assert 'x-request-id' in allowed


def test_unapproved_origin_is_not_reflected():
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ORIGIN],
        allow_credentials=True,
        allow_methods=['POST', 'OPTIONS'],
        allow_headers=_cors_headers_from_source(),
    )
    response = TestClient(app).options(
        '/api/auth/openedx-session/exchange',
        headers={
            'Origin': 'http://untrusted.example.test',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-request-id',
        },
    )
    assert response.status_code == 400
    assert response.headers.get('access-control-allow-origin') is None
