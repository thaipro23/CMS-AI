from pathlib import Path
from types import SimpleNamespace

from app.core import config

ROOT = Path(__file__).resolve().parents[3]


def _safe_settings(**overrides):
    base = dict(
        app_env='uat', debug=False, auto_create_tables=False,
        auth_mode='openedx_sso', allow_demo_role_header=False,
        auth_cookie_secure=False, allow_insecure_uat_http=True,
        auth_cookie_samesite='lax', auth_session_token_ttl_seconds=3600,
        openedx_session_bridge_max_age_seconds=60,
        auth_exchange_rate_limit_per_minute=20,
        auth_exchange_ticket_rate_limit_per_minute=3,
        redis_url='redis://redis:6379/0', jwt_secret='x' * 64,
        jwt_issuer='issuer', jwt_audience='audience', use_mock_openedx=False,
        mock_llm=False, family_plan_reconcile_on_preview=True,
        family_plan_require_all_approved=True, family_plan_hard_duplicate_guard=True,
        cors_allowed_origins='http://ai.cms-test.poly.edu.vn', metrics_enabled=False,
        metrics_token=None, database_url='postgresql+psycopg://u:p@postgres/db',
        db_pool_size=10, db_max_overflow=20, db_pool_timeout=30,
        db_statement_timeout_ms=5000, openai_api_key='sk-real',
        openedx_client_id='client', openedx_client_secret='secret',
        openedx_connector_hmac_secret='h' * 64, openedx_session_bridge_secret=None,
        celery_worker_prefetch_multiplier=1, celery_worker_max_tasks_per_child=25,
        celery_default_soft_time_limit_seconds=1500,
        celery_default_time_limit_seconds=1800,
        celery_broker_visibility_timeout_seconds=7200,
        academic_teacher_report_sync_export_max_teachers=20,
        academic_teacher_report_sync_export_max_students=1000,
        academic_ap_sync_enabled=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_env_template_restores_requested_variables():
    source = (ROOT / '.env.production.example').read_text()
    expected = {
        'ACADEMIC_AP_GET_COURSE_FILE_CACHE_ENABLED',
        'ACADEMIC_AP_GET_COURSE_FILE_CACHE_DIR',
        'ACADEMIC_AP_GET_COURSE_FILE_CACHE_TTL_SECONDS',
        'ACADEMIC_AP_GET_COURSE_FILE_CACHE_REFRESH',
        'ACADEMIC_AP_TERM_BLOCK_REFRESH_TTL_SECONDS',
        'ACADEMIC_AUTO_MAP_COURSE_BEFORE_CMS_SYNC',
        'ACADEMIC_FULL_SYNC_LEARNING_AFTER_ENROLLMENT',
        'OPENEDX_STUDENT_INSIGHT_DEFAULT_ENROLLMENT_MODE',
        'FRONTEND_URL', 'BACKEND_URL', 'OPENEDX_MFE_BASE_URL',
    }
    assert all(f'{name}=' in source for name in expected)


def test_uat_http_template_is_explicit_and_not_production():
    source = (ROOT / '.env.uat-http.example').read_text()
    assert 'APP_ENV=uat' in source
    assert 'AUTH_COOKIE_SECURE=false' in source
    assert 'ALLOW_INSECURE_UAT_HTTP=true' in source


def test_uat_http_keeps_hardened_validation(monkeypatch):
    monkeypatch.setattr(config, 'settings', _safe_settings())
    config.validate_security_settings()


def test_uat_http_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(config, 'settings', _safe_settings(allow_insecure_uat_http=False))
    try:
        config.validate_security_settings()
    except RuntimeError as exc:
        assert 'ALLOW_INSECURE_UAT_HTTP=true' in str(exc)
    else:
        raise AssertionError('Expected UAT insecure-cookie validation failure')


def test_production_never_allows_insecure_cookie(monkeypatch):
    monkeypatch.setattr(config, 'settings', _safe_settings(app_env='production'))
    try:
        config.validate_security_settings()
    except RuntimeError as exc:
        assert 'AUTH_COOKIE_SECURE=true is required in production' in str(exc)
    else:
        raise AssertionError('Expected production insecure-cookie validation failure')


def test_legacy_openedx_mfe_alias_is_used_by_publisher():
    source = (ROOT / 'backend/app/modules/publisher/service.py').read_text()
    assert "getattr(settings, 'openedx_authoring_mfe_base_url', None)" in source
    assert "getattr(settings, 'openedx_mfe_base_url', None)" in source
