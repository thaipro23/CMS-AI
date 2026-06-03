# v25.9.13.8 - Ulmo Library Publish Fix

## Mục tiêu

Sửa lỗi khi import problem vào Open edX Content Library V2 trên Tutor/Ulmo:

```txt
PublishLog matching query does not exist.
```

## Nguyên nhân

Trong Ulmo, `publish_component_changes(usage_key, user)` có thể gọi Celery publish task và chờ `result.get()`. Một số môi trường Tutor/Ulmo fail ở bước lookup `PublishLog`, dù component draft và OLX đã được lưu.

## Cách sửa

Connector không gọi `publish_component_changes` mặc định nữa. Thay vào đó:

1. `create_library_block(...)` tạo component draft.
2. `set_library_block_olx(...)` ghi OLX vào component.
3. `publish_changes(library_key, user_id=...)` publish toàn bộ pending changes ở cấp Library.

Có thể bật lại component-level publish bằng env trong CMS nếu cần:

```env
AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED=true
```

Khuyến nghị với Tutor/Ulmo:

```env
AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED=false
```

## File sửa

```txt
openedx-connector-plugin/openedx_ai_connector/views.py
```

Nếu chỉ thay file này trong CMS plugin, chỉ cần restart CMS/CMS worker, không cần build lại AI Server.

```bash
tutor local restart cms cms-worker
```

Kiểm tra:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng:

```json
{ "version": "25.9.13.8" }
```
