# v25.9.15.6.8 - Bank Generate Cost + Loading + Audit Hotfix

## Mục tiêu

Sửa các vấn đề UI/logic trong workspace ngân hàng đề theo hướng người dùng dễ hiểu:

- `prompt_cache_key` không còn vượt quá 64 ký tự.
- Người dùng nhìn thấy rõ bài/chapter hiện có bao nhiêu câu, còn bao nhiêu câu chưa duyệt/câu lỗi.
- Giới hạn 100 câu/chapter tính theo toàn bộ chapter, không chỉ một bank version.
- Bấm **Tạo câu hỏi** không gọi GPT ngay, mà mở popup xác nhận.
- Popup tạo câu hỏi hiển thị số câu EASY/MEDIUM/HARD và chi phí dự kiến.
- Có loading overlay khi đang tính chi phí hoặc đang gọi GPT tạo câu hỏi.
- Câu lỗi vì đáp án gần giống nhau (`similar_options`) không bị chặn thành `draft_error`; chỉ chặn khi đáp án trùng hẳn (`duplicate_options`).
- API trả thêm `reviewed_by`, `reviewed_at` để biết ai duyệt/ai bỏ câu.

## API mới

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/generate/preview
```

Dùng chung payload với generate:

```json
{
  "question_count": 10,
  "target_question_count": 100,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20
}
```

Response gồm:

```text
question_count
difficulty_counts
current_question_count
chapter_question_limit
remaining_quota
estimated_input_tokens
estimated_output_tokens
estimated_cost_usd
estimated_cost_vnd
model_name
```

## Luồng UI mới

```text
Bấm Tạo câu hỏi
→ backend tính preview/quota/cost
→ popup hiện:
   - số câu dễ/trung bình/khó
   - số câu hiện có trong chapter
   - số tiền dự kiến
   - Hủy / Xác nhận
→ chỉ khi xác nhận mới gọi GPT thật
```

## Lưu ý

Ước tính chi phí là estimate trước khi gọi model. Chi phí thật vẫn lấy từ usage sau khi OpenAI trả kết quả.
