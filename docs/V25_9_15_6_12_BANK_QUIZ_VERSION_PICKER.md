# v25.9.15.6.12 - Bank Quiz Version Picker by Course ID

## Mục tiêu

Sửa `/bank/quiz` để sau khi giáo viên dán Course ID, hệ thống vẫn tự nhận môn/kỳ từ Course ID nhưng không khóa cứng vào đúng kỳ đó.

Ví dụ:

```text
course-v1:FPT+WEB107+SU25
→ Môn: WEB107
→ Gợi ý version khớp: WEB107_SU25
```

UI sẽ hiện dropdown các version môn thuộc WEB107. Hệ thống pick sẵn `WEB107_SU25`, nhưng giáo viên có thể chọn `WEB107_SU24`, `WEB107_SP25`... nếu version đó đủ điều kiện.

## Điều kiện version được chọn

Một version môn chỉ được dùng để tạo Quiz khi:

```text
Tất cả Bài trong version đều có Release đã publish
Mỗi Release đã có Open edX Library key
Các câu trong Release đã có Open edX Library component id
```

Version chưa đủ điều kiện vẫn hiển thị trong dropdown để giáo viên hiểu vì sao chưa dùng được, nhưng bị disable.

## API thay đổi

Payload của 2 API auto-map có thêm:

```json
{
  "openedx_course_id": "course-v1:FPT+WEB107+SU25",
  "selected_subject_offering_id": "..."
}
```

API:

```http
POST /api/question-bank-v2/quiz/auto-map/preview
POST /api/question-bank-v2/quiz/auto-map/apply
```

Response `summary.candidates` trả danh sách version môn:

```json
{
  "offering_id": "...",
  "offering_code": "WEB107_SU25",
  "course_run_match": true,
  "all_ready": true,
  "chapter_count": 5,
  "ready_chapter_count": 5,
  "disabled_reason": null
}
```

## UI

Luồng mới:

```text
Dán Course ID
→ Hệ thống tự tìm môn WEB107
→ Hiện dropdown version môn của WEB107
→ Pick sẵn WEB107_SU25 nếu đủ điều kiện
→ Giáo viên có thể đổi sang version khác đã đủ điều kiện
→ Preview map Section ↔ Bài theo version đã chọn
→ Lưu mapping
→ Tạo Quiz
```

## File sửa

```text
backend/app/schemas/question_bank.py
backend/app/services/question_bank_service.py
backend/app/api/routes/question_bank_v2.py
frontend/app/bank/quiz/page.tsx
frontend/lib/api.ts
frontend/types/index.ts
```

Không thêm migration.
