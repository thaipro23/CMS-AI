# Batch 25 — Course-wide Quiz Advanced Settings

## Mục tiêu

Khi AI Server tạo Quiz hoặc Final test trong một Course CMS, connector phải tự động đặt và xác minh hai cấu hình tại **Course → Settings → Advanced Settings**:

- **Maximum Attempts**: `1`
- **Show Answer**: `Never` (`showanswer = "never"`)

Cấu hình áp dụng ở cấp **toàn Course**, không đặt riêng trên Subsection/Unit.

## Luồng mới

1. AI Server gọi endpoint tạo Quiz node.
2. Open edX connector tải Course draft root từ modulestore.
3. Đọc giá trị hiện tại của `max_attempts` và `showanswer`.
4. Nếu chưa đúng, cập nhật Course root.
5. Đọc lại Course root và xác minh chính xác `1` / `never`.
6. Chỉ khi xác minh thành công mới tiếp tục tạo Chapter/Sequential/Vertical cho Quiz.
7. Connector trả `course_quiz_policy_result` về AI Server.
8. AI Server kiểm tra lại contract; thiếu hoặc sai policy thì job tạo Quiz thất bại rõ ràng.

## Tính chất vận hành

- Idempotent: Course đã đúng cấu hình thì không ghi lại.
- Fail-fast: không tạo Quiz nếu Course Advanced Settings không lưu/xác minh được.
- Áp dụng cho cả Quiz và Final test.
- Không có migration database.
- Các Problem có cấu hình override riêng vẫn có thể không kế thừa default Course; Batch này thực hiện đúng yêu cầu đặt tại Course Advanced Settings.

## Response mới từ connector

```json
{
  "course_quiz_policy_result": {
    "ok": true,
    "verified": true,
    "changed": true,
    "scope": "course",
    "before": {
      "max_attempts": null,
      "showanswer": "finished"
    },
    "after": {
      "max_attempts": 1,
      "showanswer": "never"
    },
    "advanced_settings_path": "/authoring/course/course-v1:FPT+COM1071+SU26/settings/advanced"
  }
}
```

## Triển khai

Phải triển khai cả hai phía:

### AI Server

- `backend/app/services/question_bank/quiz_creation.py`
- `backend/app/modules/publisher/service.py`

Rebuild/recreate `backend` và `worker`.

### Open edX connector

- `openedx-connector-plugin/openedx_ai_connector/studio.py`

Chép file vào plugin editable đang được LMS/CMS load trong `edx-platform`, sau đó restart/recreate CMS/LMS theo cấu hình Tutor hiện tại.

## Xác minh UAT

1. Tạo Quiz mới cho `course-v1:FPT+COM1071+SU26`.
2. Mở:
   `/authoring/course/course-v1:FPT+COM1071+SU26/settings/advanced`
3. Xác nhận:
   - Maximum Attempts = 1
   - Show Answer = Never
4. Kiểm tra job response có `course_quiz_policy_result.verified = true`.

## Kiểm tra đã thực hiện

- Đã kiểm tra cú pháp AST cho toàn bộ file Python thay đổi.
- Chưa chạy unit test, Docker build hoặc UAT thực tế.
