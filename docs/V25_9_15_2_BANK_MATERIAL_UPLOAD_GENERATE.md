# v25.9.15.2 - Bank Material Upload + Generate from Bank Version

## Mục tiêu

Bản này nối tiếp kiến trúc Question Bank-first của v25.9.15.x. Giáo viên/lead bộ môn có thể upload tài liệu vào một Bank Version trước khi có khóa học Open edX, hệ thống tách nội dung thành chunks, rồi gọi GPT để sinh câu hỏi gắn trực tiếp vào Bank Version đó.

Luồng mới:

```text
Bộ môn → Môn → Chapter → Bank Version
→ Upload Material Version
→ Material Chunks
→ Generate Questions
→ Teacher Review
→ Bank Release
→ 1 Bank Release = 1 Open edX Library
```

## API mới

### Upload tài liệu vào Bank Version

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/materials/upload
Content-Type: multipart/form-data
```

Form fields:

```text
file: PDF/DOCX/PPTX/XLSX/CSV/TXT/HTML/VTT/SRT/...
title: tên tài liệu
change_type: initial | updated | replaced
replace_existing: true | false
```

Kết quả trả về số chunk và token đã index.

### Xem chunks của Bank Version

```http
GET /api/question-bank-v2/bank-versions/{bank_version_id}/material-chunks
```

### Generate câu hỏi từ Bank Version

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/generate
```

Payload:

```json
{
  "question_count": 10,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20,
  "provider": "openai",
  "approve_after_generate": false
}
```

Câu hỏi tạo ra mặc định ở trạng thái `pending_review` nếu pass quality checker, hoặc `draft_error` nếu lỗi chất lượng. Không tự approved để tránh đưa câu chưa duyệt vào Release.

### Xem câu hỏi theo Bank Version

```http
GET /api/question-bank-v2/bank-versions/{bank_version_id}/questions
```

## DB mới

Thêm bảng:

```text
ai_material_chunks
```

Các cột chính:

```text
material_version_id
bank_version_id
subject_id
chapter_id
chunk_index
content
token_count
source_type
page_number
source_ref
content_hash
```

## Nguyên tắc an toàn

- Không cho upload vào Bank Version đã `published` hoặc `archived`.
- Không sửa đè câu hỏi đã duyệt trong release cũ.
- Generate dùng `bank_version_id`, không dùng Open edX `course_id` làm chủ sở hữu.
- `course_id` trong `ai_questions` được đặt dạng kỹ thuật `bank:<bank_version_id>` để giữ tương thích bảng cũ; các field đúng của kiến trúc mới là `subject_id`, `subject_chapter_id`, `bank_version_id`, `material_version_id`, `concept_version_id`.
- Câu hỏi vẫn phải review trước khi tạo Bank Release.

## UI

Trang `/bank` có thêm bước:

```text
3. Upload tài liệu và sinh câu hỏi
```

Hiển thị:

```text
Bank Version đang chọn
Số chunk tài liệu
Token đã index
Số câu trong version
```

## Hạn chế trung thực

Bản này đã nối được upload/tách chunk/generate trực tiếp theo Bank Version. Tuy nhiên:

- Chưa có màn review riêng theo Bank Version; có API list questions, UI chỉ preview 5 câu mới nhất.
- Chưa có diff/carry-over/retire khi tài liệu đổi; phần đó dành cho v25.9.15.3.
- Generate hiện chạy trong request backend, chưa chuyển sang Celery job riêng cho Bank Version. Với tài liệu lớn nên generate từng batch nhỏ hoặc chuyển async ở bản sau.
