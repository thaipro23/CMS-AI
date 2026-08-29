# v25.9.16.7.2.64.16.5.7.1.1 — UAT Build & Backend Health Hotfix

## Purpose

Fix the two deployment failures observed after pulling `.64.16.5.7.1`:

1. Frontend Docker build stopped in `npm ci` with npm's internal `Exit handler never called!` failure.
2. Backend remained unhealthy after migration and service recreation.

## Frontend build reliability

`frontend/Dockerfile` now:

- pins npm `10.9.2` rather than relying on the Node image's npm `10.8.2`;
- uses a persistent BuildKit npm cache mount even when normal layer cache is invalidated;
- limits npm network sockets to four;
- configures bounded fetch retry and timeout values;
- retries both npm pinning and `npm ci` up to three times;
- removes partial `node_modules` between failed attempts;
- emits npm debug-log tails into Docker build output before retrying.

Compose exposes `FRONTEND_NPM_VERSION`, defaulting to `10.9.2`.

## Backend restart-loop protection

The persisted runtime settings subsystem previously applied every allowed field over `.env` before hardened validation. A runtime volume created by an older release could therefore restore values such as:

- `auth_mode=demo`;
- `allow_demo_role_header=true`;
- `use_mock_openedx=true`;
- `mock_llm=true`;
- old Open edX identity/base URL settings.

In hardened UAT and production these fields are now environment-owned and ignored when read from `runtime-settings.json`. Invalid optional persisted values are logged and skipped rather than aborting process startup. Runtime PATCH applies the same lock in UAT as in production.

## Backend health and diagnostics

- Healthcheck now uses `http.client.HTTPConnection` with Docker `CMD`, avoiding a shell heredoc.
- Startup warm-up increases from 30 to 90 seconds.
- Health interval is 10 seconds with 18 retries.
- Gunicorn access/error logs and worker output are captured on stdout/stderr.
- Python bytecode writes are disabled in the read-only runtime.

## Compatibility

- Continues directly from `.64.16.5.7.1`.
- UAT HTTP remains explicit: `APP_ENV=uat`, `AUTH_COOKIE_SECURE=false`, `ALLOW_INSECURE_UAT_HTTP=true`.
- Production still requires Secure cookies.
- No API, RBAC, Celery task, Open edX or database semantics are changed.
- No new Alembic migration; head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
