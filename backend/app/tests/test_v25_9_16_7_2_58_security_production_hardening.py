from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v58_version_sync_and_no_new_migration() -> None:
    targets = [
        'backend/app/core/config.py',
        'frontend/package.json',
        'frontend/package-lock.json',
        'frontend/Dockerfile',
        'docker-compose.prod.yml',
        '.env.example',
        '.env.production.example',
        'frontend/components/layout/AppShell.tsx',
        'README.md',
        'RUN_CURRENT.md',
        'scripts/claude-code-review-pack.sh',
        'scripts/uat-build-gate.sh',
        'scripts/uat-runtime-verify.sh',
        'scripts/security-readiness-report.sh',
    ]
    for target in targets:
        assert VERSION in text(target), target
    migrations = [p.name for p in (ROOT / 'backend/alembic/versions').glob('*.py')]
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in migrations
    assert not any(name.startswith('0053_') or name.startswith('0054_') for name in migrations)


def test_v58_security_readiness_endpoint_is_read_only_and_secret_safe() -> None:
    route = text('backend/app/api/routes/health.py')
    service = text('backend/app/services/security_readiness.py')
    assert "/health/security-readiness" in route and "SecurityReadinessReport" in route
    assert "require_permission('manage_settings')" in route
    assert 'SecurityReadinessService().report()' in route
    assert 'read_only_no_secret_values_no_mutation' in service
    for token in [
        'JWT_SECRET_STRONG',
        'DEMO_ROLE_HEADER_DISABLED',
        'CORS_EXPLICIT_WHITELIST',
        'METRICS_TOKEN_PROTECTED',
        'OPENEDX_CONNECTOR_HMAC_SECRET_STRONG',
        'DOWNLOAD_HOST_ALLOWLIST_CONFIGURED',
        'DESTRUCTIVE_IDENTITY_CLEANUP_DISABLED_IN_PRODUCTION',
    ]:
        assert token in service
    forbidden = ['.delete(', '.update(', 'analytics_class_recalculate_task.delay', 'TrackingLogReader(', 'requests.', 'httpx.']
    for term in forbidden:
        assert term not in service
    assert 'Không trả secret/token/password ra response' in service


def test_v58_frontend_surfaces_security_gate() -> None:
    page = text('frontend/app/analytics/learning/page.tsx')
    api = text('frontend/lib/api.ts')
    types = text('frontend/types/index.ts')
    css = text('frontend/app/globals.css')
    assert 'getSecurityReadiness' in api
    assert 'SecurityReadinessReport' in types
    assert 'Security production gate' in page
    assert 'analytics-security-readiness-panel' in page
    assert 'securityReadinessLabel' in page
    assert 'analytics-security-readiness-panel' in css


def test_v58_scripts_and_review_pack_cover_security_gate() -> None:
    report = text('scripts/security-readiness-report.sh')
    runtime = text('scripts/uat-runtime-verify.sh')
    review = text('scripts/claude-code-review-pack.sh')
    build_gate = text('scripts/uat-build-gate.sh')
    assert '/health/security-readiness' in report
    assert 'SECURITY_READINESS_SUMMARY.md' in report
    assert '/health/security-readiness' in runtime
    assert 'security-readiness.json' in runtime
    assert 'SecurityReadinessService' in review
    assert 'scripts/security-readiness-report.sh' in review
    assert 'scripts/security-readiness-report.sh' in build_gate
    banned = ['curl -X POST', 'curl -X DELETE', 'rm -rf', 'DROP TABLE', 'TRUNCATE TABLE']
    for term in banned:
        assert term not in report
