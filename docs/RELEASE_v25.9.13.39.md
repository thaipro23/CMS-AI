# v25.9.13.39 - Rollback Library Component Match Fix

## Mục tiêu
Sửa lỗi rollback Open edX báo đã xóa thành công nhưng component vẫn còn trong Open edX Library.

## Nguyên nhân
AI Server lưu `openedx_library_problem_id` dạng full usage key:

```text
lb:FPT:mul211-bai-2-easy:problem:ai-xxxx
```

Trong khi API `get_library_components()` của Open edX Ulmo trả `Component.key` là local id:

```text
ai-xxxx
```

Verifier cũ chỉ so sánh full usage key nên tưởng component không tồn tại và trả `already_absent`, vì vậy rollback báo thành công giả.

## Sửa đổi
- Connector CMS giờ match component bằng cả full usage key và local component key.
- Response debug có thêm `match_reason`, `local_id`, `sample_candidates` để dễ kiểm tra.
- Rollback chỉ coi absent là thành công khi đã check đúng bằng local key.

## File chính
- `openedx-connector-plugin/openedx_ai_connector/views.py`

## Cập nhật
Nếu chỉ sửa rollback Open edX, copy plugin mới vào CMS và restart:

```bash
tutor local restart cms cms-worker
```

Nếu muốn đồng bộ version AI Server:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```
