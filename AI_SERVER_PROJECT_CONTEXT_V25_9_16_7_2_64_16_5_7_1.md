# AI Server Project Context — v25.9.16.7.2.64.16.5.7.1

Canonical baseline after `.64.16.5.7`.

Key compatibility behavior:

- Production: `APP_ENV=production`, `AUTH_COOKIE_SECURE=true`, `ALLOW_INSECURE_UAT_HTTP=false`.
- HTTP UAT only: `APP_ENV=uat`, `AUTH_COOKIE_SECURE=false`, `ALLOW_INSECURE_UAT_HTTP=true`.
- UAT remains a hardened deployment; all other production-like security validation still applies.
- `.env.production.example` contains all requested legacy variables.
- `.env.uat-http.example` is the dedicated HTTP UAT template.
- `OPENEDX_AUTHORING_MFE_BASE_URL` is canonical; `OPENEDX_MFE_BASE_URL` remains accepted.
- No migration beyond `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
