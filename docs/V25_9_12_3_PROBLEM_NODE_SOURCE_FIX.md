# v25.9.12.3 - Problem Node Source Fix

Bản này sửa cách xử lý `problem` node cũ trong CMS/Open edX.

## Mục tiêu

- Không đưa problem/quiz cũ vào prompt AI theo mặc định khi generate theo scope rộng.
- Nếu giảng viên chủ động chọn problem node hoặc problem chunk thì vẫn dùng problem đó như tài liệu nguồn.
- Parse problem XML để giữ được đáp án đúng từ `correct="true"`.
- Không hiển thị metadata `filename` của CMS trong content/chunk/token/prompt.
- Node Detail hiển thị rõ đáp án đúng cho teacher/admin kiểm tra.

## Backend

### File mới

`backend/app/services/problem_parser.py`

Chức năng:

- `remove_openedx_filename_metadata()` bỏ metadata kiểu `{"filename": [...]}` hoặc `filename: [...]` khỏi nội dung học.
- `parse_problem_xml()` parse `<multiplechoiceresponse>`, `<choicegroup>`, `<choice correct="true">`.
- `build_ai_text_from_problem()` convert problem XML thành text có marker `[ĐÁP ÁN ĐÚNG]`.

### File sửa

`backend/app/services/content_extractor.py`

- Ưu tiên đọc `problem_xml` trước `data/content`.
- Với `block_type=problem`, parse XML thay vì chỉ strip HTML.
- Bỏ metadata filename khỏi text cuối.

`backend/app/services/course_sync.py`

- Giữ nguyên xuống dòng cho problem chunk nếu nội dung problem nằm trong một chunk, để Node Detail hiển thị từng câu/đáp án rõ ràng.

`backend/app/services/generation_planner.py`

- Nếu teacher chọn `chunk_ids` cụ thể: cho phép dùng problem chunk.
- Nếu teacher chọn đúng problem node: cho phép dùng problem node.
- Nếu generate mặc định hoặc chọn chapter/course rộng: loại `source_type=problem` khỏi prompt.
- Khi problem được đưa vào prompt, thêm instruction không copy nguyên văn quiz cũ.

`backend/app/modules/openedx_connector/real.py`

- Giữ raw problem XML khi normalize block để parser đọc được `correct="true"`.

`backend/app/services/token_counter.py`

- Cho phép môi trường offline không có package `tiktoken` vẫn fallback heuristic thay vì chết import.

## Frontend

`frontend/app/sync/page.tsx`

- Node Detail render nội dung problem theo từng dòng.
- Dòng có `[ĐÁP ÁN ĐÚNG]` được highlight và đổi thành `✓ Đáp án đúng`.
- Thêm notice giải thích problem cũ chỉ được dùng khi giảng viên chọn trực tiếp.

`frontend/app/globals.css`

- Thêm style cho correct answer line và notice card.

## Cách test nhanh

```bash
docker compose down
docker compose up --build
```

Sau đó:

1. Vào `/sync`.
2. Đồng bộ course.
3. Chọn node `problem` kiểu `Trắc nghiệm cuối bài`.
4. Kiểm tra Node Detail không còn `{"filename": ...}`.
5. Kiểm tra đáp án đúng hiện `✓ Đáp án đúng`.
6. Generate theo chapter/course rộng: problem cũ không bị tự động đưa vào prompt.
7. Chọn trực tiếp problem node/chunk rồi generate: problem được dùng làm source, nhưng prompt có instruction không copy nguyên văn.

## Ghi chú kiểm thử trong môi trường này

Đã chạy `python -m compileall` cho các file Python được sửa. Chưa chạy được pytest đầy đủ trong sandbox vì môi trường hiện không có dependency `sqlalchemy` được cài sẵn.
