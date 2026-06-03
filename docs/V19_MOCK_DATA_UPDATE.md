# v19 Mock Data Update

Bản này chỉnh mock data để phù hợp với các thuật toán v19.

## Đã chỉnh

### 1. Mock Open edX course tree

`backend/app/modules/openedx_connector/mock.py` giờ trả về course mock theo cấu trúc gần giống Open edX thật:

```text
Course
  ├── Chapter 1: REST API cơ bản
  │   └── Sequential
  │       ├── Unit: REST overview
  │       │   └── HTML + PDF asset text
  │       └── Unit: HTTP Methods
  │           ├── Video + transcripts
  │           └── Existing problem
  ├── Chapter 2: Entity Framework Core
  │   └── DbContext, DbSet, Migration, SaveChanges
  └── Chapter 3: AI Server cho Open edX
      └── Course Sync, Question Bank, Teacher Review, Cost Control
```

Mock data có đủ:

- `children` và `parent_block_id` để test Course Tree Traversal.
- HTML/Text component để test Content Extractor.
- Transcript SRT/VTT-like content để test transcript parsing.
- File asset text mô phỏng PDF/PPTX/handout.
- Existing problem/quiz cũ để test problem extraction.
- Nhiều chủ đề khác nhau để test Topic Extraction và Topic Coverage.

### 2. Mock LLM output

`backend/app/services/model_gateway.py` giờ không còn trả tất cả câu hỏi cùng một `source_chunk_id=mock-chunk-http-methods`.

Mock LLM sẽ parse nội dung worker gửi vào dạng:

```text
Source: ...
Type: ...
ChunkId: ...
<chunk content>
```

Sau đó tạo câu hỏi có:

- `source_ref` thật từ chunk.
- `source_type` thật.
- `source_chunk_id` là ID chunk trong database.
- `source_excerpt` lấy từ chunk.

Điều này giúp Quality Checker v19 pass được source grounding thay vì đánh `draft_error` vì source chunk không tồn tại.

### 3. Chủ đề câu hỏi mock đa dạng hơn

Mock LLM có template câu hỏi cho:

- REST API
- HTTP Methods
- Entity Framework Core
- DbContext
- DbSet
- Migration
- SaveChanges
- Course Sync
- Source Grounding
- Teacher Review
- Question Bank
- Open edX OLX Export
- Cost Control
- Quota
- Hard Stop
- Usage Log

## Cách test nhanh

```powershell
docker compose down -v
docker compose up --build
```

Sau đó vào:

```text
http://localhost:3000/sync
```

Bấm Sync course với course mặc định:

```text
course-v1:FPT+PRN232+2026
```

Kết quả mong muốn:

- Course tree có 3 chương.
- Chunks có nhiều source type: html, transcript, pdf/pptx/text/problem.
- Topics đa dạng hơn.
- Generate mock LLM tạo câu hỏi `pending_review` thay vì toàn `draft_error`.
- Question Bank có câu hỏi thuộc nhiều topic, đủ source reference.

## Lưu ý

Nếu DB đã có dữ liệu mock cũ, nên reset volume trong môi trường demo:

```powershell
docker compose down -v
docker compose up --build
```

Production không dùng `down -v`; production phải dùng Alembic migration.
