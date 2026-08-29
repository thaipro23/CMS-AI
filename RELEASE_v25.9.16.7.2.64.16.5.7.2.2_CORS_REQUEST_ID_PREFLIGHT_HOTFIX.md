# v25.9.16.7.2.64.16.5.7.2.2 — CORS Request-ID Preflight Hotfix

## Root cause

The frontend API client adds `X-Request-ID` to requests. Cross-origin browser requests therefore send a CORS OPTIONS preflight containing:

```text
Access-Control-Request-Headers: content-type,x-request-id
```

The backend CORS configuration allowed `Content-Type` but omitted `X-Request-ID`, so Starlette returned `400 Bad Request` before the SSO exchange endpoint was called.

The configured UAT origins were already correct; hosts-file mapping and `127.0.0.1` were not the cause.

## Fix

- Added `X-Request-ID` to `_base_cors_headers`.
- Added `X-Request-ID` and `X-Process-Time-Ms` to CORS exposed response headers.
- Kept the explicit `CORS_ALLOWED_ORIGINS` allowlist and credentials policy.
- Did not use wildcard origins or wildcard request headers.
- Added a behavioral OPTIONS regression test and release gate.

## Scope

- Backend-only rebuild.
- No frontend rebuild required.
- No worker restart required for code correctness, though operators may recreate workers during normal release rollout.
- No migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
