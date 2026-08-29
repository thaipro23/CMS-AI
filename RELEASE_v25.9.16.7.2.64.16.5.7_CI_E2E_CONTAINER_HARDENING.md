# v25.9.16.7.2.64.16.5.7 — CI/E2E & Container Hardening

## Mục tiêu

Biến các contract bảo mật, hiệu năng và frontend runtime của `.64.16.5.4–.64.16.5.6` thành quality gate có thể thực thi trong CI, đồng thời giảm đặc quyền và blast radius của container production.

## CI pipeline

Thêm `.github/workflows/ci.yml` với bốn job độc lập:

1. **Backend quality and integration**
   - PostgreSQL 16 + pgvector và Redis thật;
   - Python compile và Ruff fatal checks;
   - Alembic upgrade head;
   - current behavior tests và PostgreSQL/Redis integration tests;
   - downgrade về `0052`, sau đó upgrade lại `0053` trên database dùng một lần;
   - runtime-name và hardening source gates.
2. **Frontend quality**
   - `npm ci`;
   - ESLint không warning;
   - TypeScript;
   - Next.js production build và standalone assertion.
3. **Browser E2E**
   - Playwright Chromium desktop/mobile;
   - shell, responsive drawer, accessible dialog và not-found boundary;
   - upload report/evidence kể cả khi test lỗi.
4. **Container hardening**
   - build production backend/frontend images;
   - xác minh UID `10001`, source không writable và backend runtime không có compiler;
   - resolve/validate Compose migration dependency và `no-new-privileges`.

Thêm Dependabot cho npm, pip, GitHub Actions và Dockerfile.

## Browser smoke tests

Playwright nằm trong package `e2e/` riêng, không làm phình Next.js tracing/runtime dependencies. Có hai project:

- Chromium desktop;
- Chromium mobile.

API cần thiết được mock ở browser layer để kiểm tra shell/runtime contract độc lập với dữ liệu UAT. Integration với backend/Open edX thật vẫn phải kiểm tra trên UAT.

## Backend image

`backend/Dockerfile.prod` chuyển sang multi-stage:

- build wheels ở stage có toolchain;
- runtime chỉ cài dependencies cần chạy;
- không giữ `build-essential/gcc`;
- chạy UID/GID `10001`;
- source `/app` và `/source-contract` immutable;
- chỉ `/app/.runtime` là writable shared volume.

Requirements được tách:

- `requirements-runtime.txt` cho production;
- `requirements-ci.txt` cho CI;
- `requirements.txt` giữ khả năng cài môi trường dev/test hiện tại.

## Frontend image

Frontend tiếp tục multi-stage nhưng được harden thêm:

- lint, typecheck và build trong builder;
- runner non-root UID/GID `10001`;
- standalone output immutable;
- writable Next cache là tmpfs do Compose quản lý.

## Compose production

Thêm hai one-shot service:

- `runtime-init`: chuẩn bị ownership cho named runtime volume;
- `migrate`: chạy Alembic một lần.

Backend không còn chạy `alembic upgrade head && gunicorn`. API/worker phụ thuộc `service_completed_successfully` của migration job.

Application services được áp dụng:

- non-root;
- read-only root filesystem;
- `cap_drop: ALL`;
- `no-new-privileges`;
- PID, CPU và memory limits;
- tmpfs có `noexec/nosuid/nodev` khi phù hợp;
- init process và stop grace period;
- healthcheck cho các service chạy lâu dài.

## Test và gate mới

- `scripts/ci-backend-tests.sh`
- `scripts/ci-e2e-container-hardening-report.sh`
- PostgreSQL/Redis integration tests
- release contract `.64.16.5.7`
- hardening gate được tích hợp vào review pack và UAT build gate.

## Database

Không có migration mới. Alembic head vẫn là:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

## Boundary

Bản này không thay:

- API nghiệp vụ;
- Bank hierarchy hoặc Release/Quiz semantics;
- backend RBAC;
- Assignment score externalization;
- Open edX connector contract;
- schema database.
