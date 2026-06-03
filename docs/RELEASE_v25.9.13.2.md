# v25.9.13.2 - Export Preview, User Analytics, Publish Safety Fix

## Fix chính

- Sửa trang `/export`: preview OLX không còn báo thành công nhưng khung preview rỗng. Nguyên nhân là backend trả field `olx`, frontend lại đọc `olx_xml`.
- Sửa compatibility DB cho `/users`: bổ sung auto ALTER/migration cho các cột `ai_usage_log` dễ thiếu ở volume cũ.
- Sửa publish an toàn: không còn đánh dấu `published` nếu `USE_MOCK_OPENEDX=true` hoặc connector trả kết quả `mock/stub`.
- Sửa audit publish course: nếu lỗi toàn bộ thì route trả 502 thay vì ghi thành công giả.
- Plugin mẫu ghi rõ endpoint Library/Problem hiện là stub, không phải production mutation.

## Cần nhớ

Nếu muốn publish thật sang Studio/Open edX, cần:

```env
USE_MOCK_OPENEDX=false
OPENEDX_BASE_URL=http://studio.local.openedx.io
OPENEDX_PREFER_STUDIO_CONTENT=true
```

Và connector trong CMS phải có implementation thật tạo Library/Problem, không phải stub trong file `openedx-connector-plugin/openedx_ai_connector/views.py`.
