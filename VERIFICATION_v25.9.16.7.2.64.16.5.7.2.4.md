# Verification — v25.9.16.7.2.64.16.5.7.2.4

## Đã kiểm tra trong môi trường đóng gói

- SHA-256 input Batch 34 khớp canonical.
- Python `compileall`: PASS.
- Regression Batch 31–35: **24 passed**.
- TypeScript/TSX syntax transpile cho API client và trang Udemy: PASS.
- `docker-compose.prod.yml` YAML parse: PASS, 12 services.
- Celery worker hostname/healthcheck static contract: PASS.
- Alembic `heads/history` chain `0056 -> 0057`: PASS trong chế độ metadata SQLite; chưa chạy upgrade trên PostgreSQL thật.
- XLSX upload safety tests: PASS.
- Retention test, gồm bảo vệ active import source: PASS.
- Static contract xác nhận không có ACMS transfer implementation: PASS.

## Chưa thể kiểm tra trong môi trường đóng gói

- Docker production build và `docker compose config` bằng Docker Engine thực.
- Chạy migration trên PostgreSQL thật.
- Redis/Celery worker/Beat thật và retry khi hạ tầng gián đoạn.
- Browser E2E, responsive và accessibility.
- Teacher/campus owner account thật.
- Query plan với dataset 20.000+ sinh viên.
- Backup/restore UAT.

Không được coi release là production accepted cho đến khi các mục trên có evidence.
