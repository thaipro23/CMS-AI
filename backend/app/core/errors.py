from __future__ import annotations

from datetime import datetime, timezone
import logging
import sys
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, PendingRollbackError
import httpx


def error_payload(*, code: str, message: str, status_code: int, details: Any = None, request_id: str | None = None) -> dict[str, Any]:
    return {
        'error': {
            'code': code,
            'message': message,
            'status_code': status_code,
            'details': details,
            'request_id': request_id,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
    }


def _derived_code(code: str, suffix: str) -> str:
    if code.endswith('_FAILED'):
        return f'{code[:-7]}_{suffix}'
    return f'{code}_{suffix}'


def _value_error_semantics(reason: str, fallback_status: int, fallback_code: str) -> tuple[int, str]:
    normalized = reason.casefold()
    if normalized.startswith('không tìm thấy') or ' không tồn tại' in normalized:
        return 404, _derived_code(fallback_code, 'NOT_FOUND')
    conflict_markers = (
        'đã tồn tại',
        'bị trùng',
        'dữ liệu trùng',
        'đã publish',
        'đã bị khóa',
        'không thể xóa',
        'vẫn còn dữ liệu liên kết',
        'không được sửa',
    )
    if any(marker in normalized for marker in conflict_markers):
        return 409, _derived_code(fallback_code, 'CONFLICT')
    return fallback_status, fallback_code


def public_http_exception(*, status_code: int, code: str, message: str, logger_name: str | None = None) -> HTTPException:
    """Map the active exception to a truthful public HTTP response.

    Route handlers call this from ``except`` blocks. Domain ``HTTPException``
    instances must keep their original status/detail; otherwise a 404/409/403
    was previously flattened into a misleading generic 400. Unexpected server
    defects are reported as 500 instead of blaming the frontend request.
    """
    logger = logging.getLogger(logger_name or 'app.api')
    active = sys.exc_info()[1]

    if isinstance(active, HTTPException):
        logger.info('%s preserved HTTP %s: %s', code, active.status_code, active.detail)
        return active
    if isinstance(active, IntegrityError):
        logger.warning('%s conflict: %s', code, active)
        return HTTPException(
            status_code=409,
            detail={
                'code': _derived_code(code, 'CONFLICT'),
                'message': 'Dữ liệu bị trùng hoặc đang được liên kết nên không thể hoàn tất thao tác.',
            },
        )
    if isinstance(active, PendingRollbackError):
        logger.error('%s database session was left in failed transaction state', code)
        return HTTPException(status_code=500, detail={
            'code': _derived_code(code, 'DATABASE_TRANSACTION_ERROR'),
            'message': 'Phiên xử lý dữ liệu gặp lỗi giao dịch. Yêu cầu đã được hủy an toàn; vui lòng thử lại.',
        })
    if isinstance(active, OperationalError):
        logger.error('%s database unavailable: %s', code, type(active).__name__)
        return HTTPException(status_code=503, detail={
            'code': _derived_code(code, 'DATABASE_UNAVAILABLE'),
            'message': 'Cơ sở dữ liệu tạm thời không sẵn sàng. Vui lòng thử lại sau.',
        })
    if isinstance(active, DBAPIError):
        # connection_invalidated means SQLAlchemy already knows the physical
        # connection cannot be reused. Other DBAPI errors are server defects or
        # query/data problems and must not be misreported as a bad user request.
        unavailable = bool(getattr(active, 'connection_invalidated', False))
        logger.error('%s database DBAPI error unavailable=%s type=%s', code, unavailable, type(active).__name__)
        return HTTPException(status_code=503 if unavailable else 500, detail={
            'code': _derived_code(code, 'DATABASE_UNAVAILABLE' if unavailable else 'DATABASE_ERROR'),
            'message': 'Cơ sở dữ liệu tạm thời không sẵn sàng.' if unavailable else 'Hệ thống gặp lỗi khi xử lý dữ liệu.',
        })
    if isinstance(active, ValidationError):
        logger.warning('%s validation failed: %s', code, active)
        return HTTPException(
            status_code=422,
            detail={
                'code': 'VALIDATION_ERROR',
                'message': 'Dữ liệu gửi lên không hợp lệ.',
                'details': active.errors(),
            },
        )
    if isinstance(active, PermissionError):
        logger.warning('%s forbidden: %s', code, active)
        return HTTPException(status_code=403, detail={'code': 'FORBIDDEN', 'message': 'Bạn không có quyền thực hiện thao tác này.'})
    if isinstance(active, FileNotFoundError):
        logger.warning('%s not found: %s', code, active)
        return HTTPException(status_code=404, detail={'code': 'NOT_FOUND', 'message': 'Không tìm thấy dữ liệu hoặc tệp được yêu cầu.'})
    if isinstance(active, (TimeoutError, httpx.TimeoutException)):
        logger.warning('%s upstream timeout type=%s', code, type(active).__name__)
        return HTTPException(status_code=504, detail={'code': _derived_code(code, 'UPSTREAM_TIMEOUT'), 'message': 'Dịch vụ tích hợp phản hồi quá thời gian chờ.'})
    if isinstance(active, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
        logger.warning('%s upstream connection failure type=%s', code, type(active).__name__)
        return HTTPException(status_code=503, detail={'code': _derived_code(code, 'UPSTREAM_UNAVAILABLE'), 'message': 'Dịch vụ tích hợp bên ngoài tạm thời không sẵn sàng.'})
    if isinstance(active, httpx.HTTPStatusError):
        upstream_status = int(active.response.status_code) if active.response is not None else 0
        logger.warning('%s upstream HTTP error status=%s', code, upstream_status)
        mapped_status = 504 if upstream_status == 504 else 503 if upstream_status in {429, 502, 503} else 502
        return HTTPException(status_code=mapped_status, detail={'code': _derived_code(code, 'UPSTREAM_ERROR'), 'message': 'Dịch vụ tích hợp bên ngoài từ chối hoặc không hoàn tất yêu cầu.'})

    module_name = type(active).__module__ if active is not None else ''
    if module_name.startswith('requests'):
        logger.warning('%s upstream requests failure type=%s', code, type(active).__name__)
        return HTTPException(status_code=503, detail={'code': _derived_code(code, 'UPSTREAM_UNAVAILABLE'), 'message': 'Dịch vụ tích hợp bên ngoài tạm thời không sẵn sàng.'})

    if isinstance(active, ValueError):
        logger.warning('%s domain error: %s', code, active)
        reason = str(active).strip()
        safe_message = reason if reason and len(reason) <= 500 else message
        resolved_status, resolved_code = _value_error_semantics(safe_message, status_code, code)
        return HTTPException(status_code=resolved_status, detail={'code': resolved_code, 'message': safe_message})

    logger.exception('%s unexpected failure: %s', code, message)
    resolved_status = 500 if status_code == 400 else status_code
    resolved_code = _derived_code(code, 'INTERNAL_ERROR') if resolved_status >= 500 else code
    resolved_message = 'Hệ thống gặp lỗi nội bộ khi xử lý yêu cầu.' if resolved_status >= 500 else message
    return HTTPException(status_code=resolved_status, detail={'code': resolved_code, 'message': resolved_message})


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
            message='Dữ liệu gửi lên không hợp lệ.',
            status_code=422,
            details=exc.errors(),
            request_id=request_id,
        ),
    )

async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Keep unexpected failures on the same JSON envelope as handled API errors."""
    request_id = getattr(request.state, 'request_id', None) or request.headers.get('x-request-id')
    logging.getLogger('app.unhandled').exception(
        'Unhandled API exception request_id=%s path=%s',
        request_id,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code='INTERNAL_SERVER_ERROR',
            message='Hệ thống gặp lỗi nội bộ khi xử lý yêu cầu.',
            status_code=500,
            request_id=request_id,
        ),
    )

