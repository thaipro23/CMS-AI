## v25.9.13.52 - Analytics PostgreSQL GROUP BY Fix

- Fixed `/api/analytics/overview` HTTP 500 on PostgreSQL caused by duplicate SQLAlchemy bind parameters inside `coalesce(ai_questions.topic, 'unknown')` between SELECT and GROUP BY.
- Reused one labeled SQL expression with a literal SQL constant for dashboard `top_scopes`.

## v25.9.13.51 - Next.js SWC Debian Slim Fix

- Switched frontend Dockerfile from `node:20-alpine` to `node:20-bookworm-slim`.
- Fixes production Docker builds where Next.js attempts to load `@next/swc-linux-x64-gnu` but Alpine lacks `ld-linux-x86-64.so.2`.
- Keeps CMS auto session login behavior from v25.9.13.49/50.

# Changelog

## v25.9.13.50 - Auto CMS Session Login

- AI Server tự chuyển qua CMS session bridge nếu user chưa có phiên AI.
- User đã đăng nhập CMS/Open edX sẽ tự có phiên trong AI Server, không cần nhập lại JWT.
- Thêm `NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN` để bật/tắt auto-login.
- Token AI ngắn hạn chỉ lưu trong sessionStorage, không lưu localStorage.



## v25.9.13.48 - CMS session bridge SSO

- Thêm endpoint CMS plugin `/session/bridge` và `/session/me`.
- Thêm backend endpoint `/api/auth/openedx-session/exchange` để đổi CMS session ticket thành AI JWT.
- Thêm frontend callback `/auth/cms-callback` và nút “Dùng phiên CMS”.
- Cho phép user đã đăng nhập CMS/Open edX vào AI Server không cần đăng nhập lại hoặc tự dán JWT.

## v25.9.13.46 - Alembic clean rebuild fix

- Fixed backend startup failure on a clean PostgreSQL volume caused by `0002_chapter_libraries` recreating `ai_course_libraries` after `0001_initial_schema` had already created it from current SQLAlchemy metadata.
- Made `0002_chapter_libraries` idempotent for table, columns and legacy unique constraint creation.

## v25.9.13.45 - Frontend standalone Docker fix

- Enabled `output: 'standalone'` in `frontend/next.config.js` so Docker can copy `.next/standalone` after `next build`.
- Kept production Docker runtime on `node server.js` from the standalone output.


## v25.9.13.44 - Frontend Docker Build Fix

- Fix frontend Docker build failure `sh: tsc: not found`.
- Force Docker deps stage to install build dependencies with `npm ci --include=dev`.
- Verify `tsc` and `next` binaries in the image before build.
- Normalize frontend package-lock resolved URLs to npm public registry for clean local rebuilds.


## v25.9.13.43 - Full rebuild hardening

- Fixed SQLAlchemy metadata startup issue in `QuestionEmbedding` indexes.
- Rebuilt production Docker/Compose flow for clean builds: PostgreSQL, Redis, backend, worker and production Next.js frontend.
- Added stronger production config validation for DB/OpenAI/Open edX OAuth placeholders.
- Added from-scratch deployment guide and helper scripts for secrets/Tutor CMS env injection.

## v25.9.13.42 - Scale and maintainability pass

- Added production composite indexes for question, job, chunk, course sync, usage and publish queries.
- Added explicit Open edX lifecycle fields so teacher review status is no longer overloaded with publish/verify/delete state.
- Added Idempotency-Key handling for generation, course publish, single-question publish and rollback flows.
- Added row-lock guards for generation and publish/rollback state transitions.
- Moved analytics dashboard aggregation from Python list aggregation to SQL aggregation.
- Changed upload validation to stream uploaded files in bounded chunks before parsing.
- Added standardized API error envelope and CI quality gates.
- Split the large Sync page by moving reusable sync tree/search/content widgets to `components/sync/SyncCourseWidgets.tsx`.

See `docs/RELEASE_v25.9.13.42_SCALE_MAINTAINABILITY.md` for deployment notes.

## v25.9.13.53 - Level 1 same-server Tutor network deployment

- Changed production compose to run AI Server as separate containers on the Tutor/Open edX Docker network.
- Removed direct host port publishing from production backend/frontend; reverse proxy should route to `ai-backend:8000` and `ai-frontend:3000`.
- Added stable container names and network aliases for Caddy/Nginx routing.
- Added Tutor Caddy reverse proxy plugin and Caddy/Nginx snippets.
- Added Level 1 deployment guide and network health-check script.
