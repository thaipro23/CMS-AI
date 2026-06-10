# v25.9.15.6.15 - Complete Custom Timed Practice Quiz Runtime

Bản này chốt runtime cho quiz tự luyện có thời gian theo hướng custom timer, không dùng native Timed Exam.

## Thành phần

- AI Server v25.9.15.6.14 đã có cấu hình timer khi tạo Quiz.
- `openedx_unit_reset` v0.4.1 lưu timer config/session, auto-submit runtime JS, lock và server-side submit guard.
- `frontend-app-learning` branch `mfe-unit-reset` đã được cập nhật để hiển thị đồng hồ, gọi start/status/timeout/lock/reset.

## Quy tắc FPT giữ nguyên

- Section: `Bài 1` → Subsection quiz: `Quiz 1`
- Section: `Bài 1.1` → Subsection quiz: `Quiz 1.1`
- Unit luôn tên: `Quiz`
- Grade as: `Quiz`
- Không dùng native Timed Exam.

## Deploy

AI Server vẫn chạy theo lệnh cũ:

```bash
cd /opt/ai-server
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache backend worker frontend
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

Plugin và Learning MFE xem file `RUN_OPENEDX_UNIT_RESET_V0_4_1.md` trong gói plugin.
