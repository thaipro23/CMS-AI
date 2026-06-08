# v25.9.15.3 Test Report

## Đã chạy trong môi trường tạo artifact

```text
python3 -m compileall -q backend/app backend/alembic: PASS
```

## Chưa chạy trong môi trường tạo artifact

- Pytest đầy đủ: môi trường tạo artifact không có đầy đủ dependency project như SQLAlchemy.
- Frontend typecheck/build: môi trường tạo artifact không có `node_modules`.
- Test database thật: cần chạy trong container backend của bạn sau khi build.

## Test nên chạy sau khi build

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend \
  alembic upgrade head

docker compose -f docker-compose.prod.yml --env-file .env.production exec backend \
  pytest app/tests/test_v25_9_15_3_version_diff_carry_over_retire.py -q -vv
```

## Luồng test tay

1. Clear DB test nếu cần.
2. Tạo Bộ môn / Môn / Chapter.
3. Tạo Bank Version v1.0.
4. Upload tài liệu và generate câu hỏi.
5. Approve một vài câu.
6. Tạo Bank Version v2.0 với `based_on_version_id` là v1.0.
7. Upload tài liệu mới vào v2.0.
8. Bấm so sánh version.
9. Carry-over candidate sang v2.0.
10. Kiểm tra câu mới có `is_carry_over=true`, `previous_question_id`, `question_revision_no`.
11. Retire một số câu cũ.
12. Tạo Release v2.0 chỉ sau khi review câu carry-over.
