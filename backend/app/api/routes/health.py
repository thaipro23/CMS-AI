from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.rbac import UserContext, require_permission
from app.db.session import engine
from app.services.openedx_student_insight import OpenEdXConnectorClient

router = APIRouter()


@router.get('/health')
def health():
    return {'status': 'ok', 'version': settings.app_version}


@router.get('/health/db')
def db_health(user: UserContext = Depends(require_permission('manage_settings'))):
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


@router.get('/health/build')
def build_health():
    """Build/runtime identity used by smoke tests after deployment."""
    return {
        'status': 'ok',
        'app_name': settings.app_name,
        'version': settings.app_version,
        'app_env': settings.app_env,
        'debug': settings.debug,
    }


@router.get('/health/openedx-connector/config')
def openedx_connector_config_health(user: UserContext = Depends(require_permission('manage_settings'))):
    """Safe connector configuration summary; never expose secrets."""
    client = OpenEdXConnectorClient()
    return {
        'status': 'ok' if client.configured() else 'not_configured',
        'configured': client.configured(),
        'base_url_set': bool(client.base_url),
        'hmac_secret_set': bool(client.connector_secret),
        'class_analytics_endpoint': client.class_analytics_endpoint,
        'users_resolve_endpoint': client.users_resolve_endpoint,
        'course_search_endpoint': client.course_search_endpoint,
        'timeout_seconds': client.timeout_seconds,
    }


@router.get('/health/analytics')
def analytics_health(user: UserContext = Depends(require_permission('view_jobs'))):
    """Read-only analytics runtime check for production smoke tests."""
    from pathlib import Path
    from app.db.session import SessionLocal
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService

    db = SessionLocal()
    try:
        status_payload = LearningAnalyticsCoreService(db).ops_status()
        file_path = status_payload.get('ingest', {}).get('file_path') or settings.openedx_tracking_log_path
        file_exists = Path(str(file_path)).exists()
        return {
            'status': 'ok',
            'version': settings.app_version,
            'analytics_ingest_enabled': settings.analytics_ingest_enabled,
            'analytics_ingest_scheduler_enabled': settings.analytics_ingest_scheduler_enabled,
            'tracking_log_path': file_path,
            'tracking_log_exists': file_exists,
            'tracking_event_count': status_payload.get('tracking_event_count', 0),
            'behavior_snapshot_count': status_payload.get('behavior_snapshot_count', 0),
            'active_recalculate_jobs': status_payload.get('active_recalculate_jobs', 0),
            'data_quality_readiness': status_payload.get('data_quality_readiness'),
            'data_quality_issue_count': status_payload.get('data_quality_issue_count'),
            'production_readiness': status_payload.get('production_readiness'),
            'ready_for_production': status_payload.get('ready_for_production'),
            'production_blocker_count': status_payload.get('production_blocker_count'),
            'production_warning_count': status_payload.get('production_warning_count'),
            'rollout_status': status_payload.get('rollout_status'),
            'rollout_mode': status_payload.get('rollout_mode'),
            'monitoring_status': status_payload.get('monitoring_status'),
            'stuck_analytics_job_count': status_payload.get('stuck_analytics_job_count'),
            'stale_snapshot_count': status_payload.get('stale_snapshot_count'),
            'safe_policy': 'signals_only_not_violation',
        }
    finally:
        db.close()
