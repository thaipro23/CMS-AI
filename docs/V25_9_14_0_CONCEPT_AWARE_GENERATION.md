# v25.9.14.0 - Concept-Aware Generation

## Mục tiêu

Bản này thêm lớp **Concept / vấn đề học tập** giữa chunk học liệu và câu hỏi AI. Mục tiêu là giảm tình trạng generate nhiều câu khác cách hỏi nhưng cùng một gốc nội dung.

Luồng mới:

```txt
Course node/chunks
→ Extract Concepts
→ Prompt generation có concept hints
→ Question lưu concept_id/concept_title/concept_key
```

## Backend thay đổi

### Model mới

`backend/app/models/concept.py`

Bảng mới:

```txt
ai_concepts
- id
- course_id
- chapter_node_id
- source_node_id
- source_node_title
- concept_key
- title
- summary
- learning_objective
- difficulty_hint
- importance_score
- source_chunk_ids
- source_evidence
- token_count
- status
- metadata_json
```

### Cột mới trong `ai_questions`

```txt
concept_id
concept_title
concept_key
```

### Service mới

`backend/app/services/concept_service.py`

Bản này dùng heuristic extractor ổn định, không gọi GPT thêm trong bước extract để tránh tăng chi phí. Khi generate, planner tự thêm `Concept-aware generation hints` vào prompt nếu node đã có nội dung.

### API mới

```http
GET /api/courses/{course_id}/concepts?node_id=...
POST /api/courses/{course_id}/concepts/extract
```

Payload extract:

```json
{
  "node_id": "block-v1:...",
  "force": false,
  "max_concepts": 20
}
```

## Frontend thay đổi

Trang `/sync` thêm panel nhỏ trong chi tiết node:

```txt
Concept / vấn đề học tập
- Trích xuất concept
- Làm lại
- Danh sách concept + difficulty hint
```

## Generation thay đổi

`backend/app/services/generation_planner.py` tự tạo hoặc tái dùng concept cho node được chọn, rồi prefix nội dung gửi GPT bằng concept hints. Prompt và structured output đã có thêm:

```json
{
  "concept_id": "...",
  "concept_title": "...",
  "concept_key": "..."
}
```

## Cách chạy

Dev/demo dùng auto create table:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

Production dùng Alembic:

```bash
docker compose exec backend alembic upgrade head
```

## Test nhanh

```bash
curl -X POST "http://localhost:8000/api/courses/course-v1:FPT+MUL211+SU26/concepts/extract" \
  -H "Content-Type: application/json" \
  -H "X-Demo-Role: admin" \
  -d '{"node_id":"all","force":false,"max_concepts":20}'
```

Kỳ vọng: trả về danh sách concepts có title/learning_objective/difficulty_hint.

## Ghi chú

Bản này chưa chặn trùng concept trong một Problem Bank. Phần đó sẽ nằm ở các bản sau:

```txt
v25.9.14.1 - Question Family ID
v25.9.14.2 - Balanced Problem Bank Export
v25.9.14.3 - Duplicate Concept Guard
```
