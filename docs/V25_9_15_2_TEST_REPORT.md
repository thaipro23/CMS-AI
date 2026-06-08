# v25.9.15.2 Test Report

## Đã chạy trong môi trường artifact

```text
python3 -m compileall -q backend/app backend/alembic: PASS
python3 -m py_compile backend/app/tests/test_v25_9_15_2_bank_material_generate_contract.py: PASS
```

## Chưa chạy được tại môi trường artifact

```text
pytest: chưa chạy vì môi trường artifact không cài dependency project như SQLAlchemy/FastAPI.
frontend npm typecheck/build: chưa chạy vì không có node_modules và môi trường artifact không tải npm package từ internet.
Docker build: chưa chạy vì artifact runtime không có Docker daemon.
OpenAI real generate: chưa chạy vì không dùng secret thật trong artifact.
```

## Lệnh test sau khi build trên server của bạn

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend \
  pytest app/tests/test_v25_9_15_2_bank_material_generate_contract.py -q -vv
```

## Luồng test thủ công

1. Clear DB AI Server nếu đang test.
2. `alembic upgrade head`.
3. Vào `/bank` tạo Bộ môn/Môn/Chapter/Bank Version.
4. Upload file PDF/DOCX/PPTX/TXT vào Bank Version.
5. Kiểm tra chunk/token hiển thị.
6. Generate 3-5 câu trước.
7. Kiểm tra câu ở API `/bank-versions/{id}/questions`.
8. Review/approve câu.
9. Tạo Release và Publish Library bằng v25.9.15.1 wiring.
