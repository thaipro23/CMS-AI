# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16

Baseline mới nhất bắt buộc:

```text
v25.9.16.7.2.64.16 — App Shell & Enterprise UI Rebuild + Production UI Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.16-app-shell-enterprise-ui-production.zip
root: ai_server_openedx_v25_9_16_7_2_64_16
```

Tiếp tục trực tiếp từ `.64.15`; không quay lại baseline cũ.

## Thay đổi chính

- AppShell/sidebar/topbar/theme được làm lại theo React + TypeScript, không dùng template legacy.
- Sidebar 64/220px desktop; mobile drawer có focus management.
- Navigation ẩn theo permission và giữ backend RBAC/scope hiện tại.
- `PageHeader` và semantic design tokens chuẩn hóa giao diện enterprise toàn hệ thống.
- Bảng dùng chung geometry/style, body không scroll ngang.
- Production ẩn giao diện test/UAT/diagnostics qua `NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false`.
- `/ops/readiness` frontend production trả 404.
- Không có demo username/course mặc định trong production.

## Boundary giữ nguyên

- Không fake dữ liệu.
- Không reset DB, xóa volume hoặc sửa tay Alembic.
- Latest migration: `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Bank: Department → Subject → một Subject Version cuối/term → Chapter → Question.
- Release/Quiz là workflow đầu ra.
- Assignment score write không được khôi phục.
- Tác vụ nặng tiếp tục chạy Celery.
- Backend enforce RBAC; frontend chỉ hiển thị capability được phép.
