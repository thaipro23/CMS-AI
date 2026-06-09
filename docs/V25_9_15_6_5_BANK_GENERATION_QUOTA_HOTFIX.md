# v25.9.15.6.5 - Bank Generation Flow + Chapter Quota Hotfix

## Mục tiêu

Sửa luồng tạo câu hỏi trong Bank-first để giống nguyên tắc course-first trước đây: tạo từ nội dung học liệu thật, có phân bổ độ khó, kiểm tra chất lượng và chống trùng trước khi đưa vào danh sách duyệt.

## Đã sửa

- UI tạo câu hỏi trong Chapter Workspace hiển thị rõ nguồn tạo là tài liệu đã gắn.
- Không dùng ngôn ngữ quiz ở bước tạo câu hỏi ngân hàng.
- Giới hạn mặc định 100 câu/chapter.
- Quota tính cả `draft_error`, `pending_review`, `approved`, `published`; chỉ câu `rejected` không tính vào quota dùng được.
- Backend chặn vượt 100 câu/chapter.
- Backend chặn tỷ lệ EASY/MEDIUM/HARD nếu tổng không bằng 100%.
- Bank MaterialChunk được format theo kiểu Source/Type/ChunkId/BlockId giống course-first.
- Không còn false `draft_error` do `source_chunk_id` của Bank MaterialChunk bị QualityChecker hiểu nhầm là Course ContentChunk.

## Chạy lại

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache backend worker frontend
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```
