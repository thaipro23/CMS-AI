from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.4'


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_version_contract():
    assert VERSION in read('backend/app/core/config.py')
    assert VERSION in read('frontend/package.json')
    assert VERSION in read('.env.production.example')


def test_diff_preview_is_read_only_and_persist_endpoint_is_privileged():
    schema = read('backend/app/schemas/question_bank.py')
    routes = read('backend/app/api/routes/question_bank_v2.py')
    service = read('backend/app/services/question_bank_service.py')
    assert 'persist: bool = False' in schema
    assert "persist=False" in routes
    assert "'/bank-versions/{bank_version_id}/diffs'" in routes
    assert "require_permission('edit_questions')" in routes
    assert 'def create_bank_version_diff' in service
    assert 'idempotency_key' in service
    assert 'except IntegrityError' in service


def test_cookie_only_one_time_sso_contract():
    auth = read('backend/app/api/routes/auth.py')
    connector = read('openedx-connector-plugin/openedx_ai_connector/studio.py')
    frontend = read('frontend/context/AppContext.tsx')
    assert 'response_model_exclude_none=True' in auth
    assert 'access_token=None if is_production() else token' in auth
    assert 'claim_bridge_ticket_once' in auth
    assert "@router.post('/logout')" in auth
    assert "'jti': str(uuid.uuid4())" in connector
    assert "const sessionToken = !IS_PRODUCTION" in frontend


def test_exception_content_is_not_returned_to_clients():
    route_root = ROOT / 'backend/app/api/routes'
    assert not any('detail=str(exc)' in path.read_text(encoding='utf-8') for path in route_root.glob('*.py'))
    assert 'def public_http_exception' in read('backend/app/core/errors.py')


def test_migration_chain_adds_diff_idempotency():
    migration = read('backend/alembic/versions/0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py')
    assert "down_revision = '0052_v25_9_16_7_2_27'" in migration
    assert 'uq_ai_bank_version_diff_idempotency' in migration


def test_table_contract_accepts_ten_rows_and_default_visibility():
    assert 'new Set([10, 20, 50, 100])' in read('frontend/hooks/useUrlTableState.ts')
    table = read('frontend/components/table/EnterpriseDataTable.tsx')
    assert 'column.defaultVisible !== false' in table
    assert 'Mặc định' in table


def test_production_auth_limits_and_logout_ui_contract():
    config = read('backend/app/core/config.py')
    shell = read('frontend/components/layout/AppShell.tsx')
    context = read('frontend/context/AppContext.tsx')
    logged_out = read('frontend/app/auth/logged-out/page.tsx')
    assert 'AUTH_SESSION_TOKEN_TTL_SECONDS must be between 900 and 7200 seconds' in config
    assert 'OPENEDX_SESSION_BRIDGE_MAX_AGE_SECONDS must be between 30 and 60 seconds' in config
    assert 'AUTH_COOKIE_SECURE=true is required in production' in config
    assert 'logoutAuthSession' in shell
    assert 'clearAuthSession' in context
    assert "pathname.startsWith('/auth/')" in shell
    assert 'Phiên AI Server đã được thu hồi' in logged_out
