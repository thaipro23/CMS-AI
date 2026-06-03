# v25.9.13.3 - Real Open edX Library Publish Connector

## Mục tiêu

Bản này thay endpoint publish stub trong `openedx-connector-plugin` bằng connector publish thật theo Content Libraries V2 Python API của Open edX.

Các endpoint publish không còn dùng `_LIBRARIES_BY_KEY` hoặc `_PROBLEMS_BY_KEY` trong memory nữa. Nếu CMS/Open edX chưa có Content Libraries V2 API hoặc chưa xác định được Studio user để publish, endpoint sẽ trả lỗi rõ ràng và AI Server không đánh dấu câu hỏi là `published`.

## Endpoint giữ nguyên

AI Server vẫn gọi các endpoint cũ:

- `POST /api/ai-connector/v1/courses/{course_id}/libraries`
- `POST /api/ai-connector/v1/libraries/{library_key}/problems`
- `POST /api/ai-connector/v1/courses/{course_id}/problems` cho legacy/direct publish

## Cách publish thật

Connector chạy bên trong CMS/Studio và thử dùng:

- `openedx.core.djangoapps.content_libraries.api.libraries.create_library`
- `openedx.core.djangoapps.content_libraries.api.libraries.get_library`
- `openedx.core.djangoapps.content_libraries.api.blocks.create_library_block`
- `openedx.core.djangoapps.content_libraries.api.blocks.set_library_block_olx`
- `openedx.core.djangoapps.content_libraries.api.blocks.publish_component_changes`
- `openedx.core.djangoapps.content_libraries.api.libraries.publish_changes`

Local AI Server library key như `DBI102-chuong-1-easy` được normalize thành Content Libraries V2 key dạng:

```txt
lib:FPT:dbi102-chuong-1-easy
```

Problem được import thành component key dạng:

```txt
lb:FPT:dbi102-chuong-1-easy:problem:ai-<question_id>
```

## Env mới cho CMS connector

Các biến này cần được set trong CMS/Studio container nếu request OAuth client_credentials vào plugin không có `request.user` bình thường:

```env
AI_CONNECTOR_PUBLISH_USERNAME=<studio_staff_or_admin_username>
AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH=false
```

Không bật `AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH=true` trong production.

## Lưu ý Ulmo / Verawood

- Nếu Open edX đang dùng bản có Content Libraries V2 API, connector sẽ tạo Library và import Problem thật.
- Nếu bản đang chạy chỉ có Legacy Library hoặc chưa bật Content Libraries V2, connector sẽ trả lỗi `Open edX Content Libraries V2 Python API không khả dụng...`.
- Bản này không báo thành công giả. Nếu lỗi, câu hỏi vẫn giữ `approved` để publish lại sau khi sửa connector/Open edX.

## Cách test nhanh

Trong AI Server:

```bash
docker compose build --no-cache backend worker frontend
docker compose up
```

Trong Tutor/CMS, cần cài lại hoặc mount lại plugin rồi restart CMS:

```bash
tutor local restart cms cms-worker
```

Kiểm tra plugin:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Sau đó vào `/export`, bấm `Xem trước OLX đã duyệt`, rồi `Publish câu đã duyệt sang Open edX`.

Nếu publish thành công thật, response/audit sẽ có:

```json
{
  "implementation": "content_libraries_v2_python_api",
  "stub": false,
  "library_key": "lib:FPT:...",
  "openedx_library_problem_id": "lb:FPT:...:problem:..."
}
```

Nếu Open edX chưa hỗ trợ API, UI sẽ báo lỗi 502 và audit log sẽ ghi nguyên nhân thật.
