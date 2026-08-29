# Changelog

## v25.9.16.7.2.64.16.5.7.2.16 — AP Sync Selected Subject Scope

- `/ap-sync` chỉ đồng bộ các môn đã chọn CMS hoặc Udemy tại `/subject-management`.
- Môn `Chưa chọn` không còn bị gọi `/get-data-cms` khi chạy phạm vi toàn hệ/toàn cơ sở.
- Backend tự enforce tập môn đã chọn; client không thể truyền mã môn chưa được chọn để lách phạm vi.
- UI hiển thị tổng số môn sẽ đồng bộ và số CMS/Udemy trước khi enqueue job.
- Request job lưu danh sách mã môn cụ thể để worker dùng phạm vi bất biến sau khi enqueue.
- Không thay đổi schema database và không tạo migration mới.

## v25.9.16.7.2.64.16.5.7.2.8 — Batch 35.3.1

- Sửa static export của `/student-management/cms` và `/student-management/udemy`.
- Hai route import trực tiếp `StudentManagementPlatformPage` thay vì import nhầm từ `../page`.
- Bổ sung Suspense fallback đồng nhất với module giảng viên.
- Bổ sung regression khóa route import/export contract.
- Không có migration và không thay đổi dữ liệu.

## v25.9.16.7.2.64.16.5.7.2.7 — Batch 35.3

- Tách Vận hành đào tạo thành 4 module CMS/Udemy cho sinh viên và giảng viên.
- Enforce `learning_platform` xuyên suốt API, service, cache và export nền.
- Giữ Quản lý môn học theo học kỳ; lớp và nghiệp vụ chi tiết vẫn theo Block.
- Route cũ mặc định CMS; không có migration mới.

## v25.9.16.7.2.64.16.5.7.2.6 — Batch 35.2

- Fix PostgreSQL `GroupingError` on the Subject Delivery list by reusing one literal-safe branch grouping expression.
- Subject Management now groups by Hệ + Học kỳ, without a Block selector.
- Selecting CMS, Udemy or Chưa chọn updates all Block deliveries of that subject in the selected semester.
- Classes, Udemy plan/progress/import and CMS/Open edX workflows remain Block-scoped.
- New semesters carry forward consistent platform choices from the nearest previous semester so users do not reselect from scratch.
- No migration and no legacy ACMS transfer.

## v25.9.16.7.2.64.16.5.7.2.5 — Batch 35.1

- Khép audit UI/UX Udemy: button contrast, alert filter semantics, persistent import/export, enterprise tables/notices, accessibility và responsive browser contracts.
- Không có migration mới và không chuyển dữ liệu ACMS cũ.

# v25.9.16.7.2.64.16.5.7.2.4 — Batch 35 Udemy Production Hardening

- Hardens Udemy `.xlsx` upload with configurable bounds, OpenXML validation and zip-bomb/path traversal defenses.
- Adds Redis rate limits for import/retry/export operations.
- Adds persistent background Udemy export, RBAC recheck, F5 recovery and retained download artifacts.
- Adds resilient Celery import/export retry, scheduled artifact cleanup and exact worker healthchecks.
- Adds index-only Alembic migration 0057 for large Udemy dashboard/export queries.
- Explicitly does not implement legacy ACMS data transfer.

# v25.9.16.7.2.64.16.5.7.2.3 — Frontend Visual Ergonomics & Navigation Hotfix

- Adds clickable Bank hierarchy breadcrumbs to the fixed topbar and removes large in-content back cards.
- Removes Chapter duplicate KPI and QA publish/rollback sections; action buttons carry the useful counts.
- Normalizes excessive bold typography, especially in question review.
- Restores two-column Quiz/Final configuration and removes duplicate Quiz/History actions.
- Fixes Student vertical scrolling and Teacher sticky-filter/avatar/action overlap regressions.
- No migration; Alembic head remains 0053.

# v25.9.16.7.2.64.16.5.7.2.2 — CORS Request-ID Preflight Hotfix

- Allows frontend `X-Request-ID` in FastAPI CORS preflight requests.
- Exposes `X-Request-ID` and `X-Process-Time-Ms` response headers to browser clients.
- Adds behavioral OPTIONS regression coverage for the Open edX session exchange endpoint.
- Preserves explicit origin allowlisting; no wildcard CORS is introduced.
- No migration; Alembic head remains 0053.

# v25.9.16.7.2.64.16.5.7.2.1 — Public npm Lockfile & Project Handoff Hotfix

- Replaced 369 OpenAI-internal Artifactory `resolved` URLs across frontend/E2E lockfiles with npm public registry URLs.
- Added `.npmrc` files and Docker/CI public registry enforcement.
- Added fail-fast lockfile registry gate and project handoff context.
- No migration; Alembic head remains 0053.

# v25.9.16.7.2.64.16.5.7.2 — Full Frontend Design Contract Closure

- Applies one frontend design contract across AppShell, Bank, Semesters, Student/Teacher navigation, Analytics tables and Users/RBAC instead of route-by-route CSS patches.
- Makes the sidebar/workspace viewport-fixed, removes Question Search from navigation and removes in-content breadcrumbs; the topbar is the single page-title/context owner.
- Rebuilds Semesters around one section header and a six-column enterprise table; removes duplicated KPI/table summaries and prevents block editors from overlapping.
- Consolidates Bank dashboard controls into one responsive toolbar; compacts Chapter statistics into contextual actions while keeping Concept/Source opt-in through column visibility.
- Moves Course CMS auto-map into the subject-list section, standardizes nested back actions and migrates the student-class detail/search/analytics detail tables to `EnterpriseDataTable`.
- Moves role assignment to a centered multi-scope dialog and adds an atomic batch RBAC endpoint; legacy `CAMPUS_MANAGER` cannot be granted anew.
- Keeps normal UAT Docker builds fast by skipping duplicated lint/typecheck in-image by default and disabling the child webpack build worker that stalled constrained hosts.
- No database migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.

# v25.9.16.7.2.64.16.5.7.1 — CI/E2E & Container Hardening

- Added enforceable GitHub CI for PostgreSQL/Redis integration, frontend quality, Playwright smoke and production images.
- Added desktop/mobile Playwright smoke tests in a standalone `e2e/` package.
- Added multi-stage non-root backend image and immutable non-root frontend runtime.
- Separated Alembic migration into a one-shot Compose service and added explicit runtime-volume initialization.
- Added read-only filesystems, dropped capabilities, no-new-privileges, resource/PID limits, tmpfs and healthchecks.
- Added runtime/CI dependency separation, integration tests, Dependabot and a 16-check hardening gate.
- No database migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.

# v25.9.16.7.2.64.16.5.7.1 — Frontend Runtime Contracts + Modal/Error Boundary

- Centralized every active modal and drawer on `AccessibleDialog` with focus trap, initial focus, nested-dialog stack, Escape, focus return and nested-safe body scroll locking.
- Removed native `alert()` and `confirm()`; added centralized toast and confirmation feedback.
- Added App Router `loading.tsx`, `error.tsx`, `global-error.tsx` and `not-found.tsx`.
- Implemented `EnterpriseDataTable` runtime contracts for `defaultVisible`, `truncateLines` and accessible server-side sorting.
- Migrated Bank, Quiz, Question Review, Student detail, Analytics, AP Sync, Premises, Semesters and question editing dialogs to the shared primitive.
- Added frontend runtime contract gate to review pack and UAT build gate.
- No database migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.

## v25.9.16.7.2.64.16.5.7.1

- Restored omitted production env variables and legacy aliases.
- Added hardened HTTP-UAT mode with explicit insecure-cookie opt-in.
- Production continues to require Secure cookies.
