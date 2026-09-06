from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session
from app.core.rbac import UserContext
from app.models.audit import AuditLog


class AuditErrorType:
    USER_ERROR = 'USER_ERROR'
    SYSTEM_ERROR = 'SYSTEM_ERROR'
    EXTERNAL_SERVICE_ERROR = 'EXTERNAL_SERVICE_ERROR'
    VALIDATION_ERROR = 'VALIDATION_ERROR'
    AUTH_ERROR = 'AUTH_ERROR'


_ERROR_TYPE_ALIASES = {
    None: None,
    '': None,
    'user': AuditErrorType.USER_ERROR,
    'user_error': AuditErrorType.USER_ERROR,
    'USER': AuditErrorType.USER_ERROR,
    'USER_ERROR': AuditErrorType.USER_ERROR,
    'system': AuditErrorType.SYSTEM_ERROR,
    'system_error': AuditErrorType.SYSTEM_ERROR,
    'SYSTEM': AuditErrorType.SYSTEM_ERROR,
    'SYSTEM_ERROR': AuditErrorType.SYSTEM_ERROR,
    'external': AuditErrorType.EXTERNAL_SERVICE_ERROR,
    'external_error': AuditErrorType.EXTERNAL_SERVICE_ERROR,
    'external_service_error': AuditErrorType.EXTERNAL_SERVICE_ERROR,
    'EXTERNAL': AuditErrorType.EXTERNAL_SERVICE_ERROR,
    'EXTERNAL_SERVICE_ERROR': AuditErrorType.EXTERNAL_SERVICE_ERROR,
    'validation': AuditErrorType.VALIDATION_ERROR,
    'validation_error': AuditErrorType.VALIDATION_ERROR,
    'VALIDATION_ERROR': AuditErrorType.VALIDATION_ERROR,
    'auth': AuditErrorType.AUTH_ERROR,
    'auth_error': AuditErrorType.AUTH_ERROR,
    'AUTH_ERROR': AuditErrorType.AUTH_ERROR,
}

_SECRET_KEYS = {'api_key', 'openai_api_key', 'client_secret', 'secret', 'token', 'access_token', 'refresh_token', 'jwt_secret', 'password'}


def normalize_error_type(error_type: str | None) -> str | None:
    if error_type is None:
        return None
    raw = str(error_type).strip()
    return _ERROR_TYPE_ALIASES.get(raw, _ERROR_TYPE_ALIASES.get(raw.lower(), raw.upper()))


def _redact_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS or any(secret in str(key).lower() for secret in ['secret', 'token', 'api_key', 'password']):
                result[key] = '***REDACTED***'
            else:
                result[key] = _redact_metadata(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def log_audit(
    db: Session,
    *,
    action: str,
    status: str = 'success',
    message: str = '',
    user: UserContext | None = None,
    actor_id: str | None = None,
    course_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """Write a best-effort audit row.

    v25.9.10 standardizes error_type to uppercase values:
    USER_ERROR, SYSTEM_ERROR, EXTERNAL_SERVICE_ERROR, VALIDATION_ERROR, AUTH_ERROR.
    Older calls using user/system/external are still accepted and normalized.
    """
    try:
        # A failed flush/commit leaves SQLAlchemy's Session inactive. Route
        # handlers still record a best-effort failure audit, so recover the
        # transaction before adding the audit row instead of producing a second
        # PendingRollbackError that hides the original API failure.
        if not db.is_active:
            db.rollback()
        row = AuditLog(
            course_id=course_id,
            actor_id=user.user_id if user else (actor_id or 'system'),
            actor_role=user.role if user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status=status,
            error_type=normalize_error_type(error_type),
            message=message[:4000] if message else '',
            metadata_json=_redact_metadata(metadata or {}),
            request_id=request_id,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
