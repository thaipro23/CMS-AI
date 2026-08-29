#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/.runtime/production-security-closure}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.2.18}"
mkdir -p "$OUT_DIR"
python - "$ROOT" "$OUT_DIR/production-security-closure.json" "$EXPECTED_VERSION" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1]); output=Path(sys.argv[2]); expected=sys.argv[3]
def read(rel): return (root/rel).read_text(encoding='utf-8')
config=read('backend/app/core/config.py')
auth=read('backend/app/api/routes/auth.py')
session=read('backend/app/core/session_security.py')
security=read('backend/app/core/security.py')
routes=read('backend/app/api/routes/question_bank_v2.py')
schema=read('backend/app/schemas/question_bank.py')
service=read('backend/app/services/question_bank_service.py')
migration=read('backend/alembic/versions/0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py')
frontend=read('frontend/context/AppContext.tsx')
shell=read('frontend/components/layout/AppShell.tsx')
api=read('frontend/lib/api.ts')
route_sources='\n'.join(p.read_text(encoding='utf-8') for p in (root/'backend/app/api/routes').glob('*.py'))
checks={
 'version': expected in config and expected in read('frontend/package.json'),
 'preview_default_read_only': 'persist: bool = False' in schema,
 'preview_forces_no_persist': "persist=False" in routes,
 'persist_endpoint_privileged': "'/bank-versions/{bank_version_id}/diffs'" in routes and "require_permission('edit_questions')" in routes and "'question.edit'" in routes,
 'deterministic_idempotency': 'idempotency_key = hashlib.sha256' in service and 'except IntegrityError' in service,
 'database_unique_constraint': 'uq_ai_bank_version_diff_idempotency' in migration and "down_revision = '0052_v25_9_16_7_2_27'" in migration,
 'cookie_only_production_exchange': 'access_token=None if is_production() else token' in auth and 'response_model_exclude_none=True' in auth,
 'one_time_bridge_ticket': 'claim_bridge_ticket_once' in auth and 'nx=True' in session and "bridge-used:{jti}" in session,
 'session_jti_revocation': "'jti': str(uuid.uuid4())" in auth and 'is_session_revoked' in security and 'session-revoked' in session,
 'exchange_rate_limit': 'enforce_fixed_window_rate_limit' in auth and 'auth-exchange-ip' in auth and 'auth-exchange-ticket' in auth,
 'bounded_auth_configuration': 'AUTH_SESSION_TOKEN_TTL_SECONDS must be between 900 and 7200 seconds' in config and 'OPENEDX_SESSION_BRIDGE_MAX_AGE_SECONDS must be between 30 and 60 seconds' in config,
 'logout_end_to_end': "@router.post('/logout')" in auth and 'logoutAuthSession' in api and 'clearAuthSession' in frontend and 'Đăng xuất' in shell,
 'production_frontend_no_bearer': 'const sessionToken = !IS_PRODUCTION' in frontend,
 'no_raw_exception_detail': 'detail=str(exc)' not in route_sources,
 'structured_public_error_helper': 'def public_http_exception' in read('backend/app/core/errors.py'),
}
status='READY' if all(checks.values()) else 'BLOCKED'
payload={'version':expected,'status':status,'passed':sum(checks.values()),'total':len(checks),'checks':checks,'note':'Source contract gate. PostgreSQL/Redis/reverse-proxy integration and browser UAT remain mandatory.'}
output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
if status!='READY': raise SystemExit(1)
PY
