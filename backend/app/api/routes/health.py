from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine

router = APIRouter()


@router.get('/health')
def health():
    return {'status': 'ok', 'version': settings.app_version}


@router.get('/health/db')
def db_health():
    """Lightweight DB readiness check for production deploy verification.

    Do not expose secrets or raw connection URLs. The pool status string is useful
    during scale tuning and safe enough for internal authenticated infrastructure
    checks; the route still lives under the private AI backend network in the
    recommended deployment.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        pool = engine.pool
        return {
            'status': 'ok',
            'database': 'reachable',
            'pool': getattr(pool, 'status', lambda: 'n/a')(),
            'db_pool_size': settings.db_pool_size,
            'db_max_overflow': settings.db_max_overflow,
            'db_pool_timeout': settings.db_pool_timeout,
            'db_pool_recycle': settings.db_pool_recycle,
            'db_statement_timeout_ms': settings.db_statement_timeout_ms,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={'status': 'error', 'database': 'unreachable', 'error_type': exc.__class__.__name__},
        )
