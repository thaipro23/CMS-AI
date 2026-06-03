# v25.9.13.43 - Full rebuild hardening

## Mục tiêu

Chuẩn hóa bản build lại từ đầu sau v25.9.13.42, ưu tiên không vỡ khi chạy `docker compose -f docker-compose.prod.yml up --build`.

## Sửa chính

- Sửa lỗi SQLAlchemy metadata: `QuestionEmbedding.__table_args__` không còn dùng nhầm index của bảng `ai_questions`.
- Dọn `PublishBatch.__table_args__` bị khai báo hai lần.
- Frontend Dockerfile chuyển sang production build bằng Node 20, `npm ci`, typecheck và Next build ở build-time.
- `docker-compose.prod.yml` đầy đủ PostgreSQL/Redis/backend/worker/frontend, healthcheck, network, volume, port mapping.
- `.env.production.example` thêm `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `NEXT_PUBLIC_API_BASE_URL`.
- Production validation chặn placeholder DB/OpenAI/Open edX OAuth.
- Download asset/transcript parse `Content-Length` an toàn hơn.
- Thêm script tạo secret và script sinh Tutor `docker-compose.override.yml` cho `AI_CONNECTOR_*`.
- Tag CMS quay lại có tag hiển thị `AI Learning Check`, `difficulty:easy`, `source:*` để test và UI filter ổn định.

## Kiểm tra đã chạy

```text
python -m compileall backend/app openedx-connector-plugin/openedx_ai_connector: PASS
backend pytest: 25 passed, 2 skipped
frontend npm run typecheck: PASS
SQLAlchemy metadata import/create_all với SQLite memory: PASS
Alembic offline SQL generation tới head: PASS
Production config safe import: PASS
Production config unsafe fail-fast: PASS
```

## Ghi chú

Trong sandbox, `npm run build` với Node 22 có thể không thoát sau bước `Collecting build traces`; Dockerfile production dùng Node 20 để tránh khác biệt môi trường. Khi build thật nên dùng Docker hoặc Node 20.
