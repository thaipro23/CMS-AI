# v25.9.14.6.1 — Parent Locator String Hotfix

## Lỗi thật trên Ulmo.3

`cms.djangoapps.contentstore.xblock_storage_handlers.create_xblock.create_xblock()` nhận `parent_locator` dưới dạng chuỗi serialized usage key. Bản 25.9.14.6 truyền trực tiếp `BlockUsageLocator`, khiến `usage_key_with_run()` gọi `UsageKey.from_string()` trên object và lỗi:

```
AttributeError: 'BlockUsageLocator' object has no attribute 'partition'
```

Lỗi xảy ra trước khi tạo ItemBank nên `rollback: []` là đúng và không có block mới từ các request lỗi này.

## Sửa

Cả hai lệnh native `create_xblock` giờ truyền chuỗi usage key sạch:

```python
parent_locator=_clean_usage_key(getattr(unit_block, 'location', unit_block))
parent_locator=_clean_usage_key(getattr(bank, 'location', bank))
```

Luồng vẫn là native Ulmo:

- Tạo `itembank` dưới Unit.
- Tạo `problem` child dưới ItemBank.
- Gán Library V2 upstream và gọi `sync_library_content`.
- Verify và rollback nếu thất bại.

## Triển khai

Chỉ sửa CMS connector plugin. Copy `openedx-connector-plugin/openedx_ai_connector/views.py` vào plugin đang chạy và restart `cms cms-worker`. Không cần build lại AI Server hoặc chạy migration.
