# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.36

## Baseline mới nhất

```text
v25.9.16.7.2.36 — Responsive Sidebar Shell Fix + Analytics Orchestrator QA
zip: ai-server-openedx-v25.9.16.7.2.36-responsive-sidebar-shell-fix-analytics-orchestrator-qa.zip
root trong zip: ai_server_openedx_v25_9_16_7_2_36
```

Bản `.36` tiếp tục từ `.35` và **không có migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Lý do phát hành

Ảnh UAT cho thấy sidebar responsive còn lỗi:

1. Desktop/laptop nhỏ hoặc khi mở DevTools: menu trái bị biến thành 2 cột trong rail hẹp, làm label bị cắt kiểu `Tổng q...`, `Ngân ...`.
2. Mobile emulation 430px: sidebar chiếm vùng rộng bất thường, tạo khoảng trống bên phải và làm nội dung `Học online` bị đẩy lệch.

## Thay đổi chính `.36`

### Sidebar/AppShell responsive

File chính:

```text
frontend/app/globals.css
```

Đã thêm block:

```text
v25.9.16.7.2.36 — responsive sidebar shell fix
```

Behavior mới:

- `>1024px`: product sidebar giữ navigation một cột ổn định.
- `<=1024px`: sidebar full-width, bounded `100vw`, nav thành thanh ngang có scroll trong khung.
- `<=480px`: nav item gọn hơn, ẩn icon để dành chỗ label.
- Ẩn `product-brand::after` trên mobile để tránh làm brand bung chiều ngang.
- Chặn page-level horizontal overflow ở `html`, `body`, `.app-layout`, `.product-shell`, `.main-area`.

### Analytics `.35` được giữ nguyên

Vẫn giữ Analytics Post-Ingest Recalculate Orchestrator:

- Sau ingest tracking.log, lấy `course_id`/`username` có event mới.
- Resolve `course_id` → `class_id` qua `AcademicClassCourseMapping`, fallback `AcademicCourseMapping`.
- Enqueue `analytics_class_recalculate_task` theo class/course.
- Không enqueue theo từng sinh viên.
- Có cooldown/cap/active job limit để không nghẽn worker/DB.

Env liên quan:

```env
ANALYTICS_POST_INGEST_RECALCULATE_ENABLED=true
ANALYTICS_POST_INGEST_RECALCULATE_COOLDOWN_SECONDS=900
ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=10
```

## Files/docs mới

```text
RUN_V25_9_16_7_2_36.md
UX_UI_CONTEXT_V25_9_16_7_2_36.md
docs/RELEASE_v25.9.16.7.2.36_RESPONSIVE_SIDEBAR_SHELL_FIX_ANALYTICS_ORCHESTRATOR_QA.md
backend/app/tests/test_v25_9_16_7_2_36_responsive_sidebar_shell_fix.py
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.36-responsive-sidebar-shell-fix-analytics-orchestrator-qa.zip -d /tmp/ai-server-v25.9.16.7.2.36
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.36/ai_server_openedx_v25_9_16_7_2_36/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Verify sau deploy

```bash
curl -sS https://api-ai.cms-test.poly.edu.vn/api/health | jq
```

Kiểm tra UI:

```text
Desktop/laptop >1024px:
- Sidebar trái một cột.
- Không còn menu 2 cột trong rail.

Mobile 430px:
- Sidebar không vượt 100vw.
- Menu là thanh ngang scroll được.
- Không có khoảng trống phải do sidebar bung width.
```
