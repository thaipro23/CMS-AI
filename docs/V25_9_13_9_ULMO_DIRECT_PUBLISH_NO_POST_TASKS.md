# v25.9.13.9 - Ulmo Direct Publish Without Post Tasks

## Mục tiêu

Fix lỗi Open edX/Tutor Ulmo khi import problem vào Content Library V2 bị lỗi:

```text
PublishLog matching query does not exist.
```

Lỗi này xảy ra sau khi tạo block và set OLX, tại bước post-publish event/index task của `content_libraries.publish_changes(...)` hoặc `publish_component_changes(...)`.

## Cách sửa

Connector không gọi public publish helper của `content_libraries` ở bước import problem nữa. Thay vào đó:

1. `create_library_block(...)`
2. `set_library_block_olx(...)`
3. Publish trực tiếp bằng `openedx_learning.api.authoring.publish_from_drafts(...)`
4. Mặc định bỏ qua post-publish event/index task để tránh lỗi `PublishLog.DoesNotExist` trên Ulmo.

## Env mới

Mặc định không cần khai báo:

```env
AI_CONNECTOR_POST_PUBLISH_EVENTS_ENABLED=false
```

Chỉ bật nếu muốn test post-publish events/index task:

```env
AI_CONNECTOR_POST_PUBLISH_EVENTS_ENABLED=true
```

Với Ulmo hiện tại nên để false.

## Cách cập nhật

Vì chỉ sửa plugin CMS, chỉ cần copy:

```text
openedx-connector-plugin/openedx_ai_connector/views.py
```

vào CMS plugin rồi restart:

```bash
tutor local restart cms cms-worker
```

Kiểm tra:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng:

```json
"version": "25.9.13.9"
```
