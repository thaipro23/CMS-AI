from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_11_version_sync_and_no_migration():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Security Attack Simulation + 20 Common Attack Hardening' in text('README.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_11_security_headers_are_global():
    headers = text('backend/app/core/security_headers.py')
    main = text('backend/app/main.py')
    assert 'apply_security_headers' in headers
    assert 'X-Content-Type-Options' in headers and 'nosniff' in headers
    assert 'X-Frame-Options' in headers and 'DENY' in headers
    assert 'Strict-Transport-Security' in headers
    assert 'Content-Security-Policy' in headers
    assert 'security_headers_middleware' in main
    assert 'apply_security_headers(response)' in main


def test_v64_11_hmac_nonce_and_replay_controls():
    real = text('backend/app/modules/openedx_connector/real.py')
    connector = text('openedx-connector-plugin/openedx_ai_connector/auth.py')
    unit_reset = text('openedx-unit-reset-plugin/openedx_unit_reset/views.py')
    assert 'secrets.token_urlsafe' in real
    assert 'X-AI-Connector-Nonce' in real
    assert '.{nonce}' in real
    assert '_check_and_store_hmac_nonce' in connector
    assert 'HTTP_X_AI_CONNECTOR_NONCE' in unit_reset
    assert 'ai_unit_reset_hmac_nonce' in unit_reset
    assert 'cache.add' in unit_reset


def test_v64_11_upload_filename_uses_safe_helper():
    helpers = text('backend/app/services/question_bank/helpers.py')
    route = text('backend/app/api/routes/question_bank_v2.py')
    assert 'def safe_upload_filename' in helpers
    assert "rsplit('/', 1)[-1]" in helpers
    assert 'safe_upload_filename(file.filename' in route
    assert ".replace('/', '_').replace" not in route


def test_v64_11_attack_simulation_endpoint_contract_and_ui():
    service = text('backend/app/services/security_attack_simulation.py')
    route = text('backend/app/api/routes/health.py')
    schema = text('backend/app/schemas/readiness.py')
    api = text('frontend/lib/api/readiness.ts')
    page = text('frontend/app/ops/readiness/page.tsx')
    assert 'SecurityAttackSimulationService' in service
    assert '20 common web/API attack' in service
    assert service.count('self._case(') >= 20
    assert "/health/security-attack-simulation" in route
    assert 'SecurityAttackSimulationReport' in schema
    assert 'getSecurityAttackSimulation' in api
    assert 'Security attack simulation' in page


def test_v64_11_scripts_and_review_pack_include_attack_simulation():
    script = text('scripts/security-attack-simulation-report.sh')
    assert 'SECURITY_ATTACK_SIMULATION_SUMMARY.md' in script
    assert '/health/security-attack-simulation' in script
    assert '20 attack controls' in script
    assert 'security-attack-simulation-report.sh' in text('scripts/uat-build-gate.sh')
    assert 'SECURITY_ATTACK_SIMULATION' in text('scripts/uat-runtime-verify.sh')
    assert 'security-attack-simulation-report.sh' in text('scripts/claude-code-review-pack.sh')
