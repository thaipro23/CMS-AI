# AI Server Project Context — v25.9.16.7.2.64.16.5.7.1.1

Canonical baseline: `v25.9.16.7.2.64.16.5.7.1.1 — UAT Build & Backend Health Hotfix`.

Continues directly from `.64.16.5.7.1`.

Key changes:

- frontend Docker npm pinned to `10.9.2` with BuildKit cache, bounded retry and failure-log output;
- hardened UAT/production ignores environment-owned security/integration fields from legacy `runtime-settings.json`;
- invalid optional persisted runtime settings no longer cause process restart loops;
- backend healthcheck uses direct Python HTTP, 90-second warm-up and captured Gunicorn logs;
- `FRONTEND_NPM_VERSION` added to env templates;
- no database migration; Alembic head remains `0053`.

Verification: focused tests 11 passed; hotfix gate 10/10; review pack 31/31; frontend lint/typecheck/build 30/30 and standalone PASS.

Next planned release after UAT deployment of this hotfix: `v25.9.16.7.2.64.16.5.7.2 — Full Frontend Design Contract Closure`.
