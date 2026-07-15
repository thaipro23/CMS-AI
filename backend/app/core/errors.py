from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_payload(*, code: str, message: str, status_code: int, details: Any = None, request_id: str | None = None) -> dict[str, Any]:
    return {
        'error': {
            'code': code,
            'message': message,
            'status_code': status_code,
            'details': details,
            'request_id': request_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
    }


def public_http_exception(*, status_code: int, code: str, message: str, logger_name: str | None = None) -> HTTPException:
    # Call only inside an except block. The active exception is logged server-side.
    logging.getLogger(logger_name or 'app.api').exception('%s: %s', code, message)
    return HTTPException(status_code=status_code, detail={'code': code, 'message': message})


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', None) or request.headers.get('x-request-id')
    detail = exc.detail
    code = 'HTTP_ERROR'
    message = str(detail)
    details = None
    if isinstance(detail, dict):
        code = str(detail.get('code') or code)
        message = str(detail.get('message') or detail.get('detail') or code)
        details = detail.get('details')
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code=code, message=message, status_code=exc.status_code, details=details, request_id=request_id),
        headers=getattr(exc, 'headers', None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, 'request_id', None) or request.headers.get('x-request-id')
    return JSONResponse(
        status_code=422,
        content=error_payload(
            code='VALIDATION_ERROR',
            message='Request validation failed',
            status_code=422,
            details=exc.errors(),
            request_id=request_id,
        ),
    )
