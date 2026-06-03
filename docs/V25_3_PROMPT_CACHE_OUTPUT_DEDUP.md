# v25.3 - Prompt Cache + Output Dedup Cache

## Mục tiêu

Giảm chi phí khi generate nhiều batch/difficulty và tránh tạo trùng câu hỏi khi retry hoặc bấm generate lại cùng nội dung.

## 1. Prompt Cache Optimizer

OpenAI prompt caching hoạt động tốt khi nhiều request có prefix giống hệt nhau. Vì vậy prompt đã được đổi cấu trúc:

```txt
Phần prefix ổn định:
- question policy
- anti-trick rules
- JSON output rules
- scope title
- selected chunks/content

Phần suffix thay đổi:
- question_count
- difficulty easy/medium/hard
- batch instruction
```

Với 20 câu mặc định 50/30/20, các request EASY/MEDIUM/HARD có cùng content prefix nên dễ có cached input tokens hơn.

Responses API payload thêm `prompt_cache_key`:

```json
{
  "model": "gpt-5-mini",
  "prompt_cache_key": "ai-openedx:<hash>",
  "instructions": "...",
  "input": "..."
}
```

Nếu một gateway/proxy chưa hỗ trợ `prompt_cache_key` và trả 400, backend tự retry không có field này để không làm hỏng generation.

## 2. Output Recovery Cache

Thêm bảng:

```txt
ai_generation_cache
```

Bảng này lưu:

```txt
cache_key
prompt_cache_key
course_id
source_node_id
chunk_hash
difficulty
question_count
model_name
raw_output_text
parsed_questions_json
question_hashes
response_id
parse_error
input_tokens
cached_input_tokens
output_tokens
hit_count
```

Cách dùng:

```txt
- Nếu model trả về thành công: lưu raw output + parsed questions.
- Nếu parse lỗi: lưu raw output + usage + parse_error để debug/recovery, không mất cost.
- Nếu user retry đúng cùng payload: lấy parsed_questions_json từ cache, không gọi OpenAI lại.
```

## 3. Duplicate Fingerprint Cache

Thêm cột:

```txt
ai_questions.question_hash
```

Hash được tính từ:

```txt
course_id + source_node_id + difficulty + normalized_question_text
```

Có unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_questions_course_hash
ON ai_questions(course_id, question_hash)
WHERE question_hash IS NOT NULL;
```

Nếu retry/cached output trả lại câu đã có, backend bỏ qua câu đó, không insert duplicate.

## 4. Actual usage vẫn là nguồn sự thật

Estimate vẫn conservative cho hard stop. Actual cost vẫn tính từ usage thật của OpenAI:

```txt
input_tokens
input_tokens_details.cached_tokens
output_tokens
```

Prompt cache savings hiển thị qua `actual_cached_input_tokens` và `usage_token_source`.

## 5. File chính đã sửa/thêm

```txt
backend/app/services/prompt_builder.py
backend/app/services/model_gateway.py
backend/app/services/generation_cache.py
backend/app/services/generation_planner.py
backend/app/services/question_service.py
backend/app/worker.py
backend/app/models/generation_cache.py
backend/app/models/question.py
backend/app/db/init_db.py
```

## Chạy lại

```bat
docker compose down
docker compose up --build
```

Nếu DB cũ thiếu table/cột:

```bat
docker compose down -v
docker compose up --build
```
