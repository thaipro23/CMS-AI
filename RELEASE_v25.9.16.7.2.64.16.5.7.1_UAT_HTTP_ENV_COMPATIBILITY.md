# v25.9.16.7.2.64.16.5.7.1 — UAT HTTP Environment Compatibility Hotfix

Continues directly from `.64.16.5.7`.

## Fixes

- Restores the 11 deployment variables omitted from `.env.production.example`.
- Keeps legacy AP get-course cache names while documenting the newer subject-CMS cache names.
- Restores `FRONTEND_URL` and `BACKEND_URL` for operational scripts.
- Adds backward-compatible `OPENEDX_MFE_BASE_URL`; canonical setting remains `OPENEDX_AUTHORING_MFE_BASE_URL`.
- Adds `.env.uat-http.example` for isolated HTTP UAT environments.
- Adds `APP_ENV=uat` hardened validation. UAT keeps production-like fail-closed validation and only permits a non-Secure cookie when `ALLOW_INSECURE_UAT_HTTP=true` is explicitly set.
- Production still rejects `AUTH_COOKIE_SECURE=false` unconditionally.

## Database

No migration. Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
