import hmac
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import api_router
from app.core.config import cors_origin_list, settings, validate_security_settings
from app.core.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.core.origin_guard import enforce_mutating_origin_guard
from app.core.security_headers import apply_security_headers
from app.db.init_db import init_db
from app.services.runtime_settings import apply_runtime_settings
from app.services.fa26_compat import (
    apply_fa26_compat_patches,
    backfill_legacy_material_preview_chunks,
    bind_quiz_constraint_request,
    reset_quiz_constraint_request,
)

apply_runtime_settings()
validate_security_settings()
apply_fa26_compat_patches()

app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
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
async def quiz_constraint_mode_middleware(request: Request, call_next):
    """Keep optional Quiz/Final constraint flags even while legacy schemas ignore extras.

    The browser sends explicit difficulty_enabled, question_type_enabled and
    question_type_weights fields. FastAPI's current request models predate these
    optional fields, so bind them request-locally before validation. The
    compatibility job-service patch persists the same fields into Celery jobs.
    """
    token = None
    path = str(request.url.path or '')
    if (
        request.method.upper() == 'POST'
        and '/question-bank-v2/releases/' in path
        and ('/quiz/preview' in path or '/quiz/create-job' in path)
    ):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            token = bind_quiz_constraint_request(payload)
    try:
        return await call_next(request)
    finally:
        reset_quiz_constraint_request(token)


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
    backfill_legacy_material_preview_chunks()


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

    if configured_token and not hmac.compare_digest(supplied_token, configured_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Invalid metrics token')
    if not configured_token and settings.app_env.lower() in {'prod', 'production'}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Metrics endpoint is not configured')

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(api_router, prefix='/api')
