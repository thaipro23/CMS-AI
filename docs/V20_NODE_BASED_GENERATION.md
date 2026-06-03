# v20 - Node-based Generation

## Lý do thay đổi

Bản v19 dùng Topic Extraction heuristic nên khi gặp tiếng Việt hoặc course thật có thể sinh topic lạ như `Dùng`, `Tải`, `Liệu`, `Giới`. Từ v20, hệ thống **không dùng topic tự đoán trong UI/generation nữa**.

## Cách mới

Hệ thống lấy trực tiếp các node dưới Open edX course:

- course
- chapter
- sequential/subsection
- vertical/unit
- html component
- video/transcript component
- file/pdf/pptx/txt asset
- problem/quiz component

Giáo viên chọn node hoặc chunks thuộc node đó để generate câu hỏi. Node trở thành phạm vi tạo câu hỏi thay vì topic.

## API mới

```http
GET /api/courses/{course_id}/nodes
GET /api/courses/{course_id}/tree
GET /api/courses/{course_id}/chunks?node_id={block_id}
POST /api/questions/generate
```

Generate request dùng:

```json
{
  "course_id": "course-v1:...",
  "question_count": 20,
  "chunk_ids": ["chunk-id-1"],
  "node_ids": ["block-v1:..."],
  "use_node_coverage": true
}
```

Các field cũ `topic` và `use_topic_coverage` vẫn được giữ ở schema để tương thích ngược, nhưng không được UI mới sử dụng.

## Thuật toán mới

- Course tree traversal: dựng cây node từ Open edX blocks.
- Node descendant filtering: chọn chapter/unit thì tự lấy mọi component con.
- Node coverage allocation: phân bổ số câu theo node có chunks/tokens.
- Source grounding: câu hỏi vẫn phải trỏ về chunk/source hợp lệ.

## UI thay đổi

- `/sync`: bỏ panel Topics, thay bằng Course Tree + Node List.
- `/generate`: bỏ Topic dropdown, thay bằng Open edX node dropdown.
- Dashboard đổi `Top topics` thành `Top nodes/scopes`.
