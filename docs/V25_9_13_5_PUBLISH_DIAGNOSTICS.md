# v25.9.13.6 - Publish Diagnostics & Empty Error Fix

Mục tiêu: sửa lỗi connector trả `openedx_library_ensure_failed` nhưng `message` rỗng và `detail` rỗng.

## Thay đổi chính

- Connector trả thêm `detail.exception_class`, `exception_repr`, `args`, `traceback_tail` khi Content Libraries V2 fail.
- Thêm endpoint an toàn để kiểm tra môi trường CMS:

```http
GET /api/ai-connector/v1/publish-diagnostics
```

Endpoint này kiểm tra:

- `LibraryLocatorV2` có tồn tại không.
- `openedx.core.djangoapps.content_libraries.api.libraries` import được không.
- `openedx.core.djangoapps.content_libraries.api.blocks` import được không.
- Có xác định được publish user không.
- Danh sách Organization short_name hiện có trong CMS.

## Lưu ý

Bản này không publish giả. Nếu Open edX Ulmo/Studio chưa bật Content Libraries V2 hoặc thiếu Organization/permission, endpoint publish sẽ fail nhưng trả lỗi rõ hơn để sửa đúng nguyên nhân.
