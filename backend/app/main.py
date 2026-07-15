import hmac
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import api_router
from app.core.config import cors_origin_list, settings, validate_security_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.origin_guard import enforce_mutating_origin_guard
from app.core.security_headers import apply_security_headers
from app.db.init_db import init_db
from app.services.runtime_settings import apply_runtime_settings

apply_runtime_settings()
validate_security_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
_base_cors_headers = ['Authorization', 'Content-Type', 'X-Requested-With', 'X-Metrics-Token', 'Idempotency-Key', 'X-Request-ID']
if (settings.app_env or '').lower() not in {'prod', 'production'} and settings.allow_demo_role_header:
    _base_cors_headers.extend(['X-User-Id', 'X-User-Role', 'X-User-Email', 'X-Course-Ids'])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=_base_cors_headers,
    expose_headers=['X-Request-ID', 'X-Process-Time-Ms'],
)


@app.middleware('http')
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get('x-request-id') or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    return response


@app.middleware('http')
async def mutating_origin_guard_middleware(request: Request, call_next):
    blocked = await enforce_mutating_origin_guard(request)
    if blocked is not None:
        return blocked
    return await call_next(request)


@app.middleware('http')
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers['X-Process-Time-Ms'] = f'{elapsed_ms:.2f}'
    return response


@app.middleware('http')
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(response)
    return response


@app.on_event('startup')
def on_startup():
    init_db()


@app.get('/metrics', include_in_schema=False)
def metrics(
    authorization: str | None = Header(default=None),
    x_metrics_token: str | None = Header(default=None),
):
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Metrics endpoint is disabled')

    configured_token = settings.metrics_token or ''
    supplied_token = x_metrics_token or ''
    if not supplied_token and authorization and authorization.lower().startswith('bearer '):
        supplied_token = authorization.split(' ', 1)[1].strip()

    # In production validate_security_settings() already enforces a strong token.
    # In dev, setting METRICS_TOKEN still protects the endpoint.
    if configured_token and not hmac.compare_digest(supplied_token, configured_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Invalid metrics token')
    if not configured_token and settings.app_env.lower() in {'prod', 'production'}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Metrics endpoint is not configured')

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(api_router, prefix='/api')
