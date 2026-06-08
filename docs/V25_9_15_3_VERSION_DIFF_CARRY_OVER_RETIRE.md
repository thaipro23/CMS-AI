# v25.9.15.3 - Version Diff / Carry-over / Retire Questions

## Mục tiêu

Bản này bổ sung bước xử lý khi tài liệu của một Chapter thay đổi. AI Server không sửa đè Bank Version hoặc câu hỏi đã duyệt/published. Thay vào đó:

1. Tạo Bank Version mới dựa trên Bank Version cũ.
2. Upload tài liệu mới vào Bank Version mới.
3. So sánh hai version.
4. Carry-over các câu còn phù hợp sang version mới.
5. Retire các câu không còn phù hợp trong version cũ hoặc version nháp.
6. Giáo viên review lại câu carry-over trước khi tạo release mới.

## Nguyên tắc dữ liệu

- Câu hỏi đã approved/published không bị sửa đè.
- Carry-over tạo một row câu hỏi mới trong Bank Version mới.
- Câu carry-over có `previous_question_id`, `lineage_root_question_id`, `question_revision_no`, `is_carry_over=true`.
- Câu retire có `is_retired=true`, `retired_reason`, `retired_at`.
- Release/course cũ không bị ảnh hưởng.

## Bảng mới

- `ai_bank_version_diffs`: lưu một lần so sánh version.
- `ai_bank_version_diff_items`: lưu các candidate theo từng concept/question.

## Cột mới trong ai_questions

- `previous_question_id`
- `lineage_root_question_id`
- `question_revision_no`
- `is_carry_over`
- `is_retired`
- `retired_reason`
- `retired_at`

## API mới

### Preview diff

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/diff/preview
```

Payload:

```json
{
  "base_bank_version_id": "<old-version-id>",
  "persist": true
}
```

Response trả về `diff_id`, mức giống tài liệu, số concept mới/thay đổi/bị bỏ, danh sách câu có thể carry-over, nên retire, hoặc cần review.

### Carry-over questions

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/carry-over
```

Payload:

```json
{
  "base_bank_version_id": "<old-version-id>",
  "question_ids": ["<optional-source-question-id>"],
  "require_review": true,
  "diff_id": "<optional-diff-id>"
}
```

Mặc định `require_review=true`, vì tài liệu đã thay đổi thì câu carry-over phải được giáo viên kiểm tra lại trước khi release.

### Retire questions

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/questions/retire
```

Payload:

```json
{
  "question_ids": ["<question-id>"],
  "reason": "Concept không còn trong tài liệu v2.0"
}
```

## UI

Trang `/bank` có thêm bước:

```text
4. So sánh version và kế thừa câu hỏi
```

Người dùng chọn version cũ và version mới, bấm so sánh. UI hiển thị:

- Độ giống tài liệu
- Số câu có thể carry-over
- Số câu nên retire
- Số câu cần review lại
- Concept mới / concept bị bỏ

Sau đó có hai nút:

- Carry-over câu còn đúng
- Retire câu không còn phù hợp

## Giới hạn hiện tại

- Diff hiện dùng rule-based comparison, content hash và SequenceMatcher, chưa gọi AI để phân loại semantic sâu.
- Carry-over mặc định cần review. Không tự approved câu carry-over khi tài liệu đã thay đổi.
- Engine chưa tự sinh câu bổ sung cho concept mới; tiếp tục dùng API generate Bank Version của v25.9.15.2.
