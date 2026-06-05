# v25.9.14.4.1 - Usage Key Normalization Hotfix

## Lỗi đã sửa

`leaf_unit_node_id` từng được trả về dưới dạng JSON-quoted string, ví dụ:

```text
"block-v1:FPT+dom123+su26+type@vertical+block@quiz-tu-luyen-de587952"
```

Open edX `UsageKey.from_string` chỉ chấp nhận chuỗi không có dấu nháy bao ngoài.

## Cách sửa

- Connector dùng canonical `str(opaque_key)` thay vì `json.dumps(..., default=str)`.
- Chuẩn hóa/unquote usage key ở mọi boundary tạo Quiz và insert Problem Bank.
- Khi retry, AI Server tự sửa row Unit local đã lưu key có dấu nháy.

## Triển khai

Copy lại `openedx-connector-plugin/openedx_ai_connector/views.py`, restart `cms cms-worker`, rồi rebuild/recreate AI backend/frontend. Không cần migration.
