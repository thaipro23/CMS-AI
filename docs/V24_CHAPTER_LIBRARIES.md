# v24 - Chapter/Module Libraries

Course không dùng một Library duy nhất nữa và cũng không tạo Library theo từng Unit. Từ v24, mỗi course tạo nhiều Library theo Chapter/Module.

Ví dụ:

- DOM1051 - Chapter 1 - REST API
- DOM1051 - Chapter 2 - Authentication
- DOM1051 - Chapter 3 - Database

## Luồng

1. AI sinh câu hỏi từ Unit/PDF/Video/HTML node hoặc chunk.
2. Backend lưu `source_node_id` là node gốc tạo câu hỏi.
3. Backend tìm Chapter cha của `source_node_id`.
4. Backend ensure Library của Chapter cha.
5. Backend import OLX vào Library Chapter.
6. Metadata `source_node_id` vẫn đi kèm câu hỏi để Problem Bank trong đúng Unit random/filter được.

## Field mới

`ai_course_libraries` và các field mới trên `ai_questions`: `source_node_id`, `source_node_title`, `chapter_node_id`, `chapter_title`, `target_library_id`, `target_library_key`, `openedx_library_problem_id`, `imported_library_at`.

## Endpoint mới

AI Server: `GET /api/libraries?course_id=...`

Open edX connector plugin contract:

- `POST /api/ai-connector/v1/courses/{course_id}/libraries`
- `POST /api/ai-connector/v1/libraries/{library_key}/problems`
