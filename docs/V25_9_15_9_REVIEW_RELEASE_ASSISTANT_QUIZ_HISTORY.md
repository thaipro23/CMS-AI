# v25.9.15.9 - Review UI + Release Assistant + Course Quiz History/Rollback

## Mục tiêu

Bản này gom 3 bước kế hoạch sau v25.9.15.6:

- v25.9.15.7: Review UI for Bank Questions
- v25.9.15.8: Release Upgrade Assistant
- v25.9.15.9: Course Quiz History / Rollback

Nguyên tắc UI: giáo viên chỉ thấy thao tác đơn giản như **Duyệt**, **Bỏ**, **Kiểm tra thay đổi**, **Chốt bộ đề**, **Rollback**. Các khái niệm kỹ thuật như family slot, itembank, release question, openedx usage key vẫn để backend xử lý.

## Luồng người dùng

```text
Clone kỳ mới
→ sửa/gắn tài liệu nếu cần
→ hệ thống báo cần kiểm tra thay đổi
→ giáo viên bấm Kiểm tra thay đổi
→ duyệt/bỏ câu hỏi
→ Release Assistant kiểm tra đã đủ điều kiện chưa
→ giáo viên bấm Chốt bộ đề
→ Publish Library
→ tạo Quiz Open edX
→ xem lịch sử Quiz / rollback khi cần
```

## Backend API mới

### Review câu hỏi trong Bank Version

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/questions/{question_id}/review
```

Payload:

```json
{
  "action": "approve",
  "note": "Giữ câu hỏi này"
}
```

`action` hỗ trợ:

```text
approve
reject
back_to_review
```

### Duyệt hàng loạt

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/questions/bulk-review
```

Payload:

```json
{
  "action": "approve",
  "approve_all_pending": true,
  "note": "Duyệt nhanh toàn bộ câu đang chờ"
}
```

### Đánh dấu thay đổi tài liệu đã xử lý

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/diff/mark-resolved
```

Payload:

```json
{
  "note": "Đã kiểm tra và xử lý thay đổi tài liệu"
}
```

### Kiểm tra trước khi chốt Release

```http
GET /api/question-bank-v2/bank-versions/{bank_version_id}/release/readiness
```

Backend trả:

```text
can_create_release
checks
stats
recommended_actions
message
```

`create_release` cũng đã có guard. Nếu còn tài liệu cần kiểm tra, câu chờ duyệt, chưa có câu approved, hoặc câu trùng gốc blocking thì không cho chốt Release.

### Lịch sử Quiz

```http
GET /api/question-bank-v2/course-quiz-instances
```

Query hỗ trợ:

```text
openedx_course_id
bank_release_id
limit
```

### Rollback Quiz

```http
POST /api/question-bank-v2/course-quiz-instances/{instance_id}/rollback
```

Payload:

```json
{
  "mode": "safe",
  "note": "Rollback từ giao diện lịch sử Quiz"
}
```

AI Server sẽ thử gọi connector để xóa Quiz node trên Open edX nếu connector hỗ trợ. Nếu không xác minh xóa được, trạng thái chuyển sang `rollback_manual_required` và UI báo cần kiểm tra/xóa thủ công trong Studio.

## Connector Open edX mới

Thêm endpoint:

```http
POST /api/ai-connector/v1/courses/{course_id}/quiz-nodes/delete
```

Endpoint này xóa một Studio draft node theo usage key và verify node đã biến mất. Đây là best-effort rollback, không giả vờ thành công nếu Open edX chưa xác nhận xóa.

## UI

### /bank

Thêm:

- Duyệt từng câu bằng nút **Duyệt**.
- Bỏ câu bằng nút **Bỏ**.
- Duyệt hết câu chờ bằng nút **Duyệt hết câu chờ**.
- Cảnh báo tài liệu đã thay đổi.
- Nút **Kiểm tra thay đổi**.
- Nút **Đánh dấu đã xử lý**.
- Release Assistant hiển thị:
  - số câu đã duyệt
  - số câu chờ duyệt
  - số câu lỗi nháp
  - việc cần làm trước khi chốt
- Nút **Chốt bộ đề** chỉ bật khi backend báo đủ điều kiện.

### /bank/quiz

Thêm:

- Lịch sử Quiz đã tạo.
- Course ID.
- trạng thái tạo Quiz.
- Unit Open edX.
- nút **Rollback**.

## File chính đã sửa

```text
backend/app/schemas/question_bank.py
backend/app/services/question_bank_service.py
backend/app/api/routes/question_bank_v2.py
backend/app/modules/openedx_connector/base.py
backend/app/modules/openedx_connector/real.py
openedx-connector-plugin/openedx_ai_connector/views.py
openedx-connector-plugin/openedx_ai_connector/urls.py
frontend/types/index.ts
frontend/lib/api.ts
frontend/app/bank/page.tsx
frontend/app/bank/quiz/page.tsx
```

## Migration

Không thêm migration mới. Dùng các cột/bảng đã có:

```text
ai_questions
ai_question_review_logs
ai_question_bank_versions.metadata_json
ai_course_quiz_instances.metadata_json/status
```

## Test đã chạy

```text
python3 -m compileall -q backend/app backend/alembic openedx-connector-plugin/openedx_ai_connector: PASS
npm ci: PASS
npm run typecheck: PASS
npm run build: compiled successfully, nhưng timeout ở bước lint/type validation cuối trong môi trường artifact
```

Chưa test rollback thật trên Open edX server. Khi đưa lên UAT cần test bằng một Quiz node thật trong Studio.
