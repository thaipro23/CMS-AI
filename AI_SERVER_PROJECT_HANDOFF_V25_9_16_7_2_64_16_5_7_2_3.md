# AI SERVER / OPEN edX CMS — PROJECT HANDOFF

## Canonical baseline

- Version: `v25.9.16.7.2.64.16.5.7.2.3 — Frontend Visual Ergonomics & Navigation Hotfix`
- Root: `ai_server_openedx_v25_9_16_7_2_64_16_5_7_2_3`
- Direct predecessor: `.64.16.5.7.2.2 — CORS Request-ID Preflight Hotfix`
- Database head: `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`
- Language: Vietnamese
- Work style: senior full-stack engineer, backend architect, senior frontend engineer and practical enterprise UX/UI reviewer.

## Paste this into the next chat

```text
Bạn là senior full-stack engineer cho dự án AI Server / Open edX CMS của FPT Polytechnic.
Stack: Next.js + TypeScript, FastAPI + SQLAlchemy, PostgreSQL, Redis + Celery.

Hãy đọc toàn bộ file project handoff và source zip đính kèm. Tiếp tục trực tiếp từ baseline canonical:
v25.9.16.7.2.64.16.5.7.2.3 — Frontend Visual Ergonomics & Navigation Hotfix.
Không dùng baseline cũ, không làm lại dự án từ đầu, không reset DB/xóa volume và không sửa tay alembic_version.
Source trong zip là nguồn sự thật cao nhất.

Ưu tiên trước mắt: deploy/smoke-test baseline mới trên UAT thật, xử lý regression có evidence và hoàn tất production acceptance. CI do người khác phụ trách; không mở rộng hoặc refactor CI nếu tôi không yêu cầu.
```

---

## Hotfix `.64.16.5.7.2.3` — Frontend Visual Ergonomics & Navigation

- Normalizes excessive bold weight across operational frontend content.
- Adds clickable Bank hierarchy breadcrumbs to the fixed topbar.
- Removes in-content Bank back-link cards from nested hierarchy pages.
- Removes Chapter duplicate KPI and QA publish/rollback blocks.
- Uses `Tạo câu hỏi (x/100)` and `Duyệt câu hỏi (n câu chờ duyệt)` action labels.
- Restores desktop two-column Quiz/Final configuration and removes duplicate Quiz/History header actions.
- Removes `Tạo Quiz trên CMS` from Bank History.
- Restores Student Management vertical scrolling.
- Makes Teacher filters static, removes teacher avatars and prevents action/notice overlap.
- No migration; Alembic head remains `0053`.

## Hotfix `.64.16.5.7.2.2` — CORS Request-ID Preflight Closure

- Fixed the browser SSO/API preflight failure caused by frontend `X-Request-ID` not being present in FastAPI CORS `allow_headers`.
- Added `X-Request-ID` to allowed request headers.
- Exposed `X-Request-ID` and `X-Process-Time-Ms` to browser JavaScript for diagnostics.
- Added a behavioral OPTIONS regression test for `http://ai.cms-test.poly.edu.vn` and `/api/auth/openedx-session/exchange`.
- Existing CORS origin allowlist remains unchanged; no wildcard origin/header was introduced.
- No frontend behavior, RBAC, SSO ticket semantics or database schema changed.
- No migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.

## 1. Mục tiêu dự án

Dự án AI Server tích hợp Open edX CMS/LMS cho FPT Polytechnic/PTCĐ, gồm hai domain độc lập:

### Question Bank

```text
Bộ môn
→ Môn học
→ một phiên bản môn cuối theo học kỳ
→ Bài/Chapter
→ Câu hỏi
→ Release
→ Open edX Library
→ Quiz/Final test trong Course CMS
```

Release và Quiz là workflow đầu ra, không phải node trong Bank hierarchy.

### Student Operations

```text
AP/CMS campus + term + subject + class
→ teacher assignment
→ student roster
→ Open edX identity/enrollment
→ learning snapshot
→ learning behavior analytics
```

Bank RBAC không tự cấp quyền xem lớp/sinh viên. Student Ops role không tự cấp quyền sửa/publish Bank.

---

## 2. Stack và môi trường

### AI Server

```text
Frontend: Next.js 14 + TypeScript
Backend: FastAPI + SQLAlchemy
DB: PostgreSQL + pgvector
Migration: Alembic
Queue/cache: Redis + Celery
Production frontend: Next standalone
Model: OpenAI Responses API, gpt-5-mini
```

### UAT hiện tại

```text
Ubuntu 24.04
Tutor 21.0.6 / Open edX Ulmo 3
AI source: /opt/ai-server
AI FE: http://ai.cms-test.poly.edu.vn
AI API: http://api-ai.cms-test.poly.edu.vn
LMS: http://cms-test.poly.edu.vn
Studio: http://scms-test.poly.edu.vn
Learning MFE: http://app.cms-test.poly.edu.vn
```

UAT hiện chạy HTTP nội bộ qua hosts/VPN, chưa phải production public HTTPS.

### UAT HTTP auth configuration bắt buộc

```env
APP_ENV=uat
AUTH_COOKIE_SECURE=false
ALLOW_INSECURE_UAT_HTTP=true
AUTH_COOKIE_SAMESITE=lax
```

Production HTTPS bắt buộc:

```env
APP_ENV=production
AUTH_COOKIE_SECURE=true
ALLOW_INSECURE_UAT_HTTP=false
```

Không bật Secure cookie khi truy cập HTTP vì browser sẽ không gửi cookie.

---

## 3. Nguyên tắc phát triển bất biến

1. Không fake dữ liệu, KPI hoặc trạng thái.
2. Không reset database, không xóa volume, không `docker compose down -v`.
3. Không sửa tay `alembic_version`.
4. Schema change phải có Alembic migration và down_revision đúng.
5. Tác vụ nặng chạy Celery; F5 không làm mất job.
6. Backend enforce RBAC; frontend hide menu/button không thay thế authorization.
7. Không đọc raw `tracking.log` trong dashboard request.
8. Không dùng wording khẳng định gian lận/vi phạm.
9. Không đưa Assignment score write trở lại AI Server.
10. Không đổi Open edX publish/enrollment semantics chỉ để refactor.
11. Không thêm Bootstrap, Metronic hoặc jQuery.
12. Không tự nâng major dependency hoặc chạy `npm audit fix --force`.
13. Source mới nhất là nguồn sự thật cho route/API/component; context chỉ định mục tiêu và boundary.

---

## 4. Design contract đã chốt

### App shell

- Sidebar tối, workspace/topbar sáng.
- Không có light/dark switch toàn trang.
- Sidebar và topbar bám viewport.
- Chỉ main content cuộn dọc; body không cuộn ngang.
- Bỏ `Tìm kiếm câu hỏi` khỏi sidebar.
- Menu không có quyền phải ẩn hoàn toàn.
- Không hiển thị footer `CMS đã kết nối` hoặc user ID ở cuối sidebar.

### Topbar và page header

- Topbar sở hữu title/context trang.
- Không render breadcrumb, eyebrow, H1 hoặc description lặp trong content.
- `Breadcrumbs` trong main content là compatibility no-op.
- Action toàn page/section phải nằm đúng ngữ cảnh; không đặt nút xa dữ liệu nó tác động.

### Action rules

- Một hoặc hai action phải hiển thị trực tiếp.
- Không giấu một action vào menu `...`.
- Action danh sách nằm bên phải section header hoặc table toolbar.
- Action record nằm ở cột Thao tác.
- Modal giữa màn hình cho create/edit/grant/review.
- Drawer bên phải chỉ cho read-only detail/log/preview nhẹ.

### Spacing/layout

```text
4 / 8 / 12 / 16 / 20 / 24 / 32px
```

- Không negative margin trong active layout.
- Không decorative absolute element đè nội dung.
- Không card lồng quá hai tầng.
- Header/action phải wrap an toàn.
- Modal footer không che form.
- Chỉ table container cuộn ngang khi thật sự cần.

### Table contract

- Dùng `EnterpriseDataTable` cho bảng nghiệp vụ lớn.
- Hiển thị đầy đủ nội dung mặc định, text dài xuống dòng.
- Không auto-hide cột quan trọng theo breakpoint.
- Cột phụ có thể `defaultVisible: false` nhưng bật lại được trong `Cột hiển thị`.
- Cột số compact; identity nhận phần không gian còn lại.
- STT ở đầu, action ở cuối.
- Server-side search/filter/sort/pagination và URL state phải được giữ.
- Page sizes: `10 / 20 / 50 / 100`.

### Status/message

- Dùng icon + text + semantic color.
- Không dùng màu làm tín hiệu duy nhất.
- Không trả raw exception cho người dùng.
- Backend canonical message contract: `ui_status`, `ui_title`, `ui_message`.

---

## 5. Các hạng mục frontend `.64.16.5.7.2` đã triển khai

### Semesters

- `Làm mới` và `Thêm học kỳ` ở bên phải section `Danh sách học kỳ`.
- Bỏ KPI strip và heading/count lặp.
- Bảng đúng sáu cột:
  - STT
  - Học kỳ
  - Lịch Block 1
  - Lịch Block 2
  - Trạng thái
  - Thao tác
- Form hai block responsive theo chiều dọc, không modal horizontal scroll.

### Bank dashboard

- Bỏ title/breadcrumb lặp trong content.
- Preset ngày, date range, phạm vi, cache status và updated time trong một toolbar responsive.
- Không còn scope strip riêng.

### Chapter/Question Review

- Bỏ KPI block Tài liệu/Tổng câu/Còn/Đã duyệt/Chờ duyệt/Bị loại/Nhóm KT/Bộ đề.
- Thông tin đưa vào action:
  - `Tài liệu (N)`
  - `Tạo câu hỏi (còn N)`
  - `Duyệt câu hỏi (N chờ)`
  - `Kiểm tra thay đổi`
  - `Chốt bộ đề (N câu)`
- `Concept` và `Nguồn` mặc định ẩn, có thể bật lại.
- Review dùng modal lớn giữa màn hình.

### Student Management

- `Tự động ghép Course CMS` nằm trong section danh sách môn.
- Contextual back action:
  - Quay lại danh sách môn
  - Quay lại danh sách lớp
- Bảng chi tiết sinh viên dùng `EnterpriseDataTable`, không còn `student-grade-table` tự dựng.

### Users/RBAC

- Gán quyền dùng modal giữa màn hình.
- Chọn nhiều môn/scope trong một lần.
- Server-side scope search, select visible, deselect và preview trước khi xác nhận.
- Không cấp mới `CAMPUS_MANAGER` legacy.
- Endpoint batch:

```text
POST /api/rbac/assignments/batch
```

Backend validate toàn bộ trước khi ghi, dedupe, một transaction, reuse assignment tồn tại và rollback toàn bộ khi lỗi.

### Các phần khác

- Bank Search và Analytics session tables dùng EnterpriseDataTable.
- Contextual back action cho route Bank lồng nhau.
- Table summary mặc định tắt để tránh lặp section title/count.
- Accessible modal runtime, route loading/error/not-found và no native alert/confirm đã có.

**Quan trọng:** các thay đổi trên đạt source/test/build trong artifact `.7.2`, nhưng vẫn cần browser UAT thật; không được coi là production-wide sign-off chỉ dựa source gate.

---

## 6. Security/performance/container work đã hoàn tất

### Security `.64.16.5.4`

- Bank diff preview không mutate DB.
- Persist endpoint tách riêng và yêu cầu write permission.
- Diff idempotency + migration `0053`.
- Production SSO cookie-only, one-time bridge ticket, Redis replay protection, rate limit, logout/revoke.
- Không trả `detail=str(exc)` trực tiếp.

### Performance `.64.16.5.5`

- Teacher export lớn chạy Celery.
- API timeout/cancellation/retry có kiểm soát.
- Polling exponential backoff.
- Celery queues: interactive/sync/generation/exports/analytics.
- Class analytics lọc event theo roster AP.
- RBAC hierarchy lazy load/server search.

### Frontend runtime `.64.16.5.6`

- Shared accessible dialog: portal, focus trap, initial focus, focus return, nested dialog, body lock.
- Route-level loading/error/global-error/not-found.
- `defaultVisible`, `truncateLines`, sort contract thực thi thật.

### Container/UAT `.64.16.5.7–.7.1.1`

- Non-root images, migration service riêng, read-only filesystem contract.
- npm `10.9.2`, retry/cache, reduced sockets.
- Hardened runtime settings: legacy runtime volume không override env security fields.
- Backend healthcheck và Gunicorn logs rõ hơn.
- HTTP UAT env compatibility giữ fail-closed cho các phần còn lại.

---

## 7. Public npm lockfile hotfix `.64.16.5.7.2.1`

### Lỗi gốc

`frontend/package-lock.json` có 365 URL và `e2e/package-lock.json` có 4 URL trỏ tới:

```text
packages.applied-caas-gateway1.internal.api.openai.org
```

UAT không truy cập được host nội bộ này nên npm `ETIMEDOUT`; `Exit handler never called!` chỉ là lỗi phụ sau timeout.

### Fix

- Toàn bộ 369 URL chuyển sang:

```text
https://registry.npmjs.org/
```

- Có `frontend/.npmrc` và `e2e/.npmrc`.
- Docker npm pin/install ép public registry.
- CI có fail-fast lockfile registry gate.
- Script:

```bash
./scripts/npm-public-registry-lockfile-report.sh
```

### Build bình thường

Không dùng `--no-cache` mỗi lần deploy.

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  build frontend backend worker worker-heavy worker-analytics beat runtime-init migrate
```

Sau đó:

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm migrate

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --no-build --force-recreate \
  frontend backend worker worker-heavy worker-analytics beat
```

CI do người khác phụ trách. Không mở rộng/refactor CI trong các phiên tiếp theo nếu người dùng không yêu cầu; chỉ giữ registry guard hiện tại để build không bị lỗi.

---

## 8. Env variables cần giữ

Các biến từng bị bỏ sót nhưng đã khôi phục:

```env
ACADEMIC_AP_GET_COURSE_FILE_CACHE_ENABLED
ACADEMIC_AP_GET_COURSE_FILE_CACHE_DIR
ACADEMIC_AP_GET_COURSE_FILE_CACHE_TTL_SECONDS
ACADEMIC_AP_GET_COURSE_FILE_CACHE_REFRESH
ACADEMIC_AP_TERM_BLOCK_REFRESH_TTL_SECONDS
ACADEMIC_AUTO_MAP_COURSE_BEFORE_CMS_SYNC
ACADEMIC_FULL_SYNC_LEARNING_AFTER_ENROLLMENT
OPENEDX_STUDENT_INSIGHT_DEFAULT_ENROLLMENT_MODE
FRONTEND_URL
BACKEND_URL
OPENEDX_MFE_BASE_URL
```

`OPENEDX_AUTHORING_MFE_BASE_URL` là tên mới được ưu tiên; `OPENEDX_MFE_BASE_URL` là alias rolling-upgrade.

---

## 9. RBAC canonical

```text
SYSTEM_ADMIN       toàn quyền hệ thống
DEPARTMENT_HEAD    full quyền nghiệp vụ trong bộ môn và node con
SUBJECT_OWNER      full quyền nghiệp vụ trong môn và node con
QUESTION_REVIEWER  quyền review trong scope được giao
CAMPUS_OWNER       xem/quản lý lớp thuộc cơ sở
TEACHER_ASSIGNED   chỉ lớp được AP phân công
CAMPUS_MANAGER     alias legacy, không cấp mới
```

Frontend phải ẩn trang/nút không có quyền. Backend vẫn kiểm tra permission và entity scope riêng.

---

## 10. Việc chưa hoàn tất / cần làm tiếp

### P0 — Deploy và smoke-test `.64.16.5.7.2.1` trên UAT

1. Pull source mới.
2. Chạy registry gate.
3. Build **không `--no-cache`**.
4. Xác nhận `npm ci` tải từ `registry.npmjs.org`, không còn ETIMEDOUT tới OpenAI internal host.
5. Chạy migrate service và recreate services.
6. Kiểm tra backend health, frontend route và SSO HTTP UAT.

### P1 — Browser UAT toàn frontend

Dùng dữ liệu và role thật, kiểm tra ít nhất Chrome/Edge và responsive 1366/768/390:

- `/bank`
- `/bank/departments`
- `/bank/chapters/{id}`
- `/bank/quiz`
- `/student-management`
- subject classes
- class detail
- `/teacher-management`
- `/analytics/learning`
- `/semesters`
- `/premises`
- `/users`
- `/jobs`
- `/audit`
- `/ap-sync`
- `/settings`

Acceptance:

- sidebar/topbar cố định;
- main-only scroll;
- không title/breadcrumb/count lặp;
- không nội dung dính/chồng;
- không body horizontal scroll;
- tables wrap đúng và đủ nội dung;
- modal không scroll ngang;
- action đúng ngữ cảnh;
- RBAC menu/button đúng role/scope.

### P1 — Analytics operational closure

Các release gần đây tập trung frontend/security/build, chưa có evidence mới xác nhận SLA Analytics đã sạch. Cần kiểm tra lại:

- event mới/giờ;
- post-ingest enqueue;
- worker recalculate;
- snapshot đầu tiên và snapshot mới/giờ;
- lớp thiếu/stale snapshot;
- backfill theo batch nhỏ;
- mapping Course CMS và roster AP.

Không queue toàn bộ hàng nghìn lớp cùng lúc.

### P1 — Production readiness

- Chuyển UAT/prod sang HTTPS trước production thật.
- `AUTH_COOKIE_SECURE=true` và CORS HTTPS.
- PostgreSQL migration `0053` verified.
- Redis replay/revocation tested.
- Load test endpoints nóng.
- Worker redelivery/time limits/shared export storage verified.
- Rollback drill và evidence pack.

### P2 — Maintainability

Sau production acceptance mới tách dần các file lớn:

```text
academic_service.py
question_bank_service.py
analytics_core_service.py
academic.py
question_bank_v2.py
globals.css / legacy CSS layers
```

Mỗi lần chỉ tách một domain, có regression trước/sau; không refactor toàn hệ thống đồng thời.

---

## 11. Những việc không được làm trong chat mới

- Không quay về `.64.13`, `.64.16` hoặc `.64.16.5.7.1.1` nếu đã có source `.7.2.1`.
- Không tạo lại frontend từ đầu.
- Không thêm Bootstrap để chữa nhanh.
- Không xóa CI chỉ vì CI không phải ưu tiên; chỉ không mở rộng nó nếu không được yêu cầu.
- Không chạy `--no-cache` theo thói quen.
- Không sửa lockfile bằng registry nội bộ của môi trường trợ lý.
- Không tuyên bố frontend hoàn tất production nếu chưa browser UAT thật.
- Không khôi phục Assignment write.
- Không cấp mới CAMPUS_MANAGER.
- Không reset/xóa DB hoặc volumes.

---

## 12. Source-of-truth order

Khi có mâu thuẫn:

1. Source trong zip `.64.16.5.7.2.1`.
2. Yêu cầu trực tiếp mới nhất của người dùng.
3. File handoff này.
4. Context/release note cũ chỉ để tham khảo lịch sử.
