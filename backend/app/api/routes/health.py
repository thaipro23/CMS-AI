from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.rbac import UserContext, require_permission
from app.db.session import engine
from app.services.openedx_student_insight import OpenEdXConnectorClient
from app.schemas.readiness import (
    MaintainabilityContractReport,
    PerformanceReadinessReport,
    PilotOperationsReport,
    ProductionReadinessReport,
    QueryHotspotReport,
    ReleaseCandidateReport,
    SecurityReadinessReport,
    SecurityAttackSimulationReport,
    ProductionPilotFinalReport,
    UxAcceptanceReport,
)

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


@router.get('/health/readiness', response_model=ProductionReadinessReport)
def production_readiness_health(user: UserContext = Depends(require_permission('view_dashboard'))):
    """Actionable production readiness gate for admins.

    Unlike /health, this is an authenticated operational checklist. It explains
    exactly which blocker/warning exists, groups issues by area, and avoids
    treating normal analytics warm-up gaps as opaque platform failures.
    """
    from app.db.session import SessionLocal
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService

    db = SessionLocal()
    try:
        report = LearningAnalyticsCoreService(db).production_readiness_report()
        http_status = 'ok' if report.get('ready_for_production') else 'not_ready'
        return {
            'status': http_status,
            'version': settings.app_version,
            'readiness': report.get('readiness'),
            'stage_status': report.get('stage_status'),
            'summary_label': report.get('summary_label'),
            'message': report.get('message'),
            'blocker_count': report.get('blocker_count'),
            'warning_count': report.get('warning_count'),
            'primary_blocker': report.get('primary_blocker'),
            'sections': report.get('sections'),
            'checks': report.get('checks'),
            'next_actions': report.get('next_actions'),
            'safe_policy': report.get('safe_policy'),
            'disclaimer': report.get('disclaimer'),
        }
    finally:
        db.close()


@router.get('/health/security-readiness', response_model=SecurityReadinessReport)
def security_readiness_health(user: UserContext = Depends(require_permission('manage_settings'))):
    """Read-only security gate for UAT/pilot/production.

    This endpoint returns configuration posture without exposing secret values.
    It does not call external services, enqueue jobs, scan raw tracking.log, or
    mutate data.
    """
    from app.services.security_readiness import SecurityReadinessService

    return SecurityReadinessService().report()


@router.get('/health/security-attack-simulation', response_model=SecurityAttackSimulationReport)
def security_attack_simulation_health(user: UserContext = Depends(require_permission('manage_settings'))):
    """Read-only static simulation for 20 common web/API attack classes.

    This endpoint does not send exploit traffic, brute-force credentials, scan
    networks, call external systems, enqueue jobs or mutate data. It verifies
    source-level controls that should stop common attack patterns before UAT.
    """
    from app.services.security_attack_simulation import SecurityAttackSimulationService

    return SecurityAttackSimulationService().report()


@router.get('/health/query-hotspots', response_model=QueryHotspotReport)
def query_hotspot_health(max_items: int = 100, user: UserContext = Depends(require_permission('view_jobs'))):
    """Read-only static query hotspot scan for load hardening review."""
    from app.services.query_hotspot import QueryHotspotService

    return QueryHotspotService().report(max_items=max(1, min(int(max_items or 100), 300)))


@router.get('/health/performance-readiness', response_model=PerformanceReadinessReport)
def performance_readiness_health(user: UserContext = Depends(require_permission('view_jobs'))):
    """Read-only performance/load gate for UAT and pilot scaling.

    This endpoint is intentionally metadata/counter based. It does not execute
    heavy plans, scan raw tracking.log, enqueue jobs, or mutate data.
    """
    from app.db.session import SessionLocal
    from app.services.performance_readiness import PerformanceReadinessService

    db = SessionLocal()
    try:
        return PerformanceReadinessService(db).performance_readiness_report()
    finally:
        db.close()


@router.get('/health/release-candidate', response_model=ReleaseCandidateReport)
def release_candidate_health(
    class_id: str | None = None,
    course_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    sample_limit: int = 5,
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    """Read-only release candidate gate for UAT/pilot sign-off.

    Composes production readiness, security readiness, performance readiness and
    UAT evidence into a single go/no-go report. It does not call external
    services, enqueue jobs, recalculate analytics, scan raw tracking.log or
    mutate data.
    """
    from app.db.session import SessionLocal
    from app.api.routes.learning_analytics import _allowed_class_ids_for_analytics
    from app.services.release_candidate import ReleaseCandidateService

    db = SessionLocal()
    try:
        allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
        return ReleaseCandidateService(db).report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=max(1, min(int(sample_limit or 5), 20)),
            allowed_class_ids=allowed_class_ids,
        )
    finally:
        db.close()


@router.get('/health/pilot-operations', response_model=PilotOperationsReport)
def pilot_operations_health(
    class_id: str | None = None,
    course_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    sample_limit: int = 5,
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    """Read-only pilot go-live runbook and rollback criteria.

    Composes the release candidate gate into phases, monitoring cadence,
    rollback triggers and sign-off requirements for controlled UAT/pilot. It
    does not call external services, enqueue jobs, recalculate analytics, scan
    raw tracking.log, publish/rollback Bank releases or mutate data.
    """
    from app.db.session import SessionLocal
    from app.api.routes.learning_analytics import _allowed_class_ids_for_analytics
    from app.services.pilot_operations import PilotOperationsService

    db = SessionLocal()
    try:
        allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
        return PilotOperationsService(db).report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=max(1, min(int(sample_limit or 5), 20)),
            allowed_class_ids=allowed_class_ids,
        )
    finally:
        db.close()


@router.get('/health/maintainability-contract', response_model=MaintainabilityContractReport)
def maintainability_contract_health(user: UserContext = Depends(require_permission('view_jobs'))):
    """Read-only maintainability/API-UI contract gate for release review."""
    from app.services.maintainability_contract import MaintainabilityContractService

    return MaintainabilityContractService().report()


@router.get('/health/uat-ux-acceptance', response_model=UxAcceptanceReport)
def uat_ux_acceptance_health(user: UserContext = Depends(require_permission('view_jobs'))):
    """Read-only static UX contract gate for Training/Ops UAT."""
    from app.services.ux_acceptance import UxAcceptanceService

    return UxAcceptanceService().report()


@router.get('/health/production-pilot-final', response_model=ProductionPilotFinalReport)
def production_pilot_final_health(
    class_id: str | None = None,
    course_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    sample_limit: int = 5,
    include_static_scans: bool = True,
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    """Read-only final QA/sign-off gate for controlled pilot rollout.

    Composes pilot operations, security, performance, query hotspot and
    maintainability gates into one final sign-off checklist. It does not run
    load tests or rollback; companion scripts create those evidence artifacts.
    """
    from app.db.session import SessionLocal
    from app.api.routes.learning_analytics import _allowed_class_ids_for_analytics
    from app.services.production_pilot_final import ProductionPilotFinalService

    db = SessionLocal()
    try:
        allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
        return ProductionPilotFinalService(db).report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=max(1, min(int(sample_limit or 5), 20)),
            allowed_class_ids=allowed_class_ids,
            include_static_scans=bool(include_static_scans),
        )
    finally:
        db.close()


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
