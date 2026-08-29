# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.2

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.2 — Bank Review & Quiz Creation Workbench
zip: ai-server-openedx-v25.9.16.7.2.64.16.2-bank-review-quiz-workbench.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_2
```

Tiếp tục từ source này; không dùng baseline cũ nếu người dùng không yêu cầu rõ ràng.

## UI contract hiện tại

- Sidebar tối cố định; topbar/content sáng.
- Không có full-app dark mode hoặc theme switcher.
- `EnterpriseDataTable` dùng column kind/priority và dense geometry.
- Ưu tiên không cuộn ngang ở 1366px bằng cách thu cột số và ẩn cột optional.
- Không thêm Bootstrap/Metronic/jQuery.
- Production ẩn diagnostics/test/mock controls.

## Bank UX `.64.16.2`

- Bank Dashboard compact, không còn marketing hero/decorative KPI circles.
- Hierarchy: Bộ môn → Môn → một Phiên bản cuối theo học kỳ → Bài → Câu hỏi.
- Hierarchy pages dùng PageHeader, filter bar gọn và cột định kiểu/ưu tiên.
- Question Review preview-first; action duyệt/từ chối/sửa trong preview drawer.
- `/bank/quiz` là workbench ba bước full-width: map course → chọn phạm vi → tạo trên CMS.
- History Quiz/Release là tabbed workspace có URL state, không dùng modal bảng lớn.
- Release và Quiz vẫn là workflow đầu ra; frozen Release membership không đổi.

## Boundary bắt buộc

- Không fake dữ liệu.
- Không reset DB, xóa volume hoặc sửa tay `alembic_version`.
- Backend enforce RBAC; frontend chỉ ẩn route/menu/action theo permission.
- Assignment score write tiếp tục externalized.
- Tác vụ nặng tiếp tục chạy Celery.
- Không đổi Open edX publish/enrollment/timer/problem-bank semantics chỉ vì UI refactor.

## Database

Không có migration mới. Latest vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Verification artifact

```text
Backend compileall: PASS
TypeScript: PASS
Release tests: 8 passed
Selected regression: 48 passed
Production build: 29/29 + standalone PASS
UX gate: READY 24/24
Security static: READY 20/20
Maintainability: 0 blocker, 6 inherited warnings
```

## Roadmap tiếp theo

Bản hợp lý tiếp theo:

```text
v25.9.16.7.2.64.16.3 — Training Operations + Analytics UX
```

Phạm vi dự kiến:

- Student list/class/detail.
- Teacher list/classes/detail.
- Analytics wizard và result/error/empty states.
- Không mở rộng Bank feature trong `.64.16.3` trừ hotfix regression.
