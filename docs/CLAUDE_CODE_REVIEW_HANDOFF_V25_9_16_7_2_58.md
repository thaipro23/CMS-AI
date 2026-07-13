# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **Security Production Hardening**.

## Files to inspect first

- `backend/app/services/security_readiness.py`
- `backend/app/api/routes/health.py`
- `frontend/app/analytics/learning/page.tsx`
- `frontend/types/index.ts`
- `frontend/lib/api.ts`
- `scripts/security-readiness-report.sh`
- `scripts/uat-runtime-verify.sh`
- `scripts/claude-code-review-pack.sh`
- `backend/app/tests/test_v25_9_16_7_2_64_2_security_production_hardening.py`

## Expected security posture

The new report is read-only and must never expose raw secrets. It should diagnose:

- unsafe `AUTH_MODE` / demo role header;
- weak/default JWT or SSO bridge secret;
- insecure cookie flags;
- wildcard/localhost/insecure public CORS;
- metrics without token;
- missing Open edX connector HMAC;
- AP/OpenAI secret readiness;
- default MinIO credentials;
- missing download host allowlist;
- destructive UAT cleanup accidentally enabled in production.

## Non-goals

- No new migration.
- No runtime secret dump.
- No Open edX/AP/OpenAI calls inside readiness request.
- No job enqueue or recalculation.
- No data mutation.
