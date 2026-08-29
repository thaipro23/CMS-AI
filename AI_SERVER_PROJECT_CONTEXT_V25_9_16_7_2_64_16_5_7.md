# AI Server / Open edX CMS — Context v25.9.16.7.2.64.16.5.7

Baseline canonical:

```text
v25.9.16.7.2.64.16.5.7 — CI/E2E & Container Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.16.5.7-ci-e2e-container-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5_7
```

Tiếp tục trực tiếp từ `.64.16.5.6`.

## Thay đổi chính

- GitHub CI có PostgreSQL/Redis integration, frontend lint/type/build, Playwright desktop/mobile và production image/Compose validation.
- Dependabot cho npm, pip, Actions và Docker.
- Playwright nằm trong package `e2e/` riêng để không làm tăng Next runtime trace.
- Backend Dockerfile multi-stage, production requirements riêng, runtime non-root UID 10001 và không có compiler.
- Frontend runtime non-root UID 10001, standalone immutable.
- Compose có `runtime-init` và `migrate` one-shot; API không tự chạy migration.
- Application services có read-only rootfs, dropped capabilities, no-new-privileges, PID/CPU/memory limits, tmpfs và healthchecks.
- Có PostgreSQL/Redis integration tests và CI/container hardening gate 16/16.

## Database

Không có migration mới. Latest migration vẫn là:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

## Verification

- Backend compileall PASS.
- ESLint PASS.
- TypeScript PASS.
- Focused tests 23 passed.
- Next.js build 30/30, standalone PASS.
- Review pack 29/29.
- Hardening gate 16/16.
- Playwright discovery 4 test case; browser run tại sandbox bị chặn bởi Chromium admin policy, phải chạy trong CI/UAT.
- Docker runtime validation chưa chạy trong sandbox vì không có Docker CLI/daemon.

## Boundary

Không thay API nghiệp vụ, backend RBAC, Bank hierarchy, Celery business semantics, Open edX connector hoặc database schema.

Roadmap hợp lý tiếp theo:

```text
v25.9.16.7.2.64.16.5.8 — Maintainability Decomposition
```

Chỉ tách module theo từng domain, có behavior/integration test bảo vệ contract; không refactor đồng thời Bank, Academic và Analytics.
