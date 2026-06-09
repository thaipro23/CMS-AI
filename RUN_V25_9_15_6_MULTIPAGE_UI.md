# Chạy v25.9.15.6 - Multi-page Bank Manager UI + Exact Clone Flow

## Build AI Server

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache backend worker frontend
```

## Migration

Bản này không thêm migration mới, nhưng vẫn nên chạy để đảm bảo DB đang ở head:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
```

## Up lại service

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

## Test nhanh

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production logs backend --tail=200
curl -i http://localhost:8000/api/health
```

## Luồng test UI

1. Mở `/bank/departments`.
2. Thêm bộ môn.
3. Click bộ môn → sang `/bank/departments/{id}/subjects`.
4. Thêm môn.
5. Click môn → sang `/bank/subjects/{id}/versions`.
6. Tạo version môn mới hoặc clone từ version cũ.
7. Click version → sang `/bank/subject-versions/{id}/chapters`.
8. Thêm bài.
9. Click bài → sang `/bank/chapters/{id}`.
10. Gắn tài liệu, tạo câu hỏi, duyệt câu hỏi, chốt Release.
11. Sang `/bank/quiz` để tạo Quiz Open edX.
12. Sang `/bank/history` để xem lịch sử và rollback nếu cần.

## Lưu ý nghiệp vụ

Clone version môn không tạo Release và không publish Open edX. Release là nút bấm tay sau khi giáo viên đã chỉnh xong tài liệu/câu hỏi.
