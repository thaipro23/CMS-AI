# v25.9.15.6.25 - Force Save Quiz Timer Config After Quiz Create

## Vấn đề

Learning MFE đã gọi đúng:

- `/api/unit-reset/v1/quiz-session/start`
- `/api/unit-reset/v1/quiz-session/status`

nhưng đồng hồ không hiện vì bảng `UnitQuizTimerConfig` trống. Quiz node được tạo trong Studio nhưng timer config không được ghi vào LMS plugin.

## Nguyên nhân

Bước save timer trước đó chỉ là best-effort trong CMS connector. Nếu CMS chưa load `openedx_unit_reset` hoặc việc save bị bỏ qua, AI Server vẫn coi Quiz tạo thành công. Kết quả là Unit tồn tại nhưng LMS không có config để start timer session.

## Sửa

Sau khi `create_quiz_node` trả về `created_nodes` và `leaf_unit_node_id`, AI Server gọi bắt buộc:

```http
POST /api/unit-reset/v1/quiz-config/upsert
```

Payload chứa:

- `course_id`
- `sequence_usage_key`
- `unit_usage_key`
- `duration_seconds`
- `cooldown_seconds`
- `auto_submit_on_timeout`
- `lock_after_timeout`

Endpoint `openedx_unit_reset` cho phép HMAC server-to-server để tránh CSRF/browser session.

## Kết quả

Quiz mới tạo sẽ có timer config thật trong LMS DB. Learning MFE mở Unit sẽ start session và hiện đồng hồ.
