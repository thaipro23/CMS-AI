# v25.9.13.36 - Open edX Rollback Usage Key Fix

## Mục tiêu
Sửa rollback Open edX bị lỗi khi AI Server gửi `problem_id`/`usage_key` có dấu nháy kép bao quanh, ví dụ:

```text
"lb:FPT:mul211-bai-3-hard:problem:ai-..."
```

Open edX connector không parse được `LibraryUsageLocatorV2` khi key còn dấu `"..."`, dẫn đến HTTP 502 và rollback một phần.

## Thay đổi chính

- Backend AI Server normalize `openedx_library_problem_id` trước khi verify/delete.
- Backend không gửi `problem_id` qua query params nữa, chỉ gửi JSON body để tránh double-encoding và log rối.
- CMS connector normalize `problem_id` nhận từ JSON/query trước khi parse usage key.
- CMS connector có thể nhận raw key, URL-encoded key hoặc JSON-encoded string key.

## File sửa

- `backend/app/modules/openedx_connector/real.py`
- `backend/app/modules/publisher/service.py`
- `openedx-connector-plugin/openedx_ai_connector/views.py`
- `backend/app/core/config.py`
- `frontend/package.json`
- `.env.example`

## Cách cập nhật

AI Server:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

CMS plugin:

```bash
tutor local restart cms cms-worker
```

Kiểm tra:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng:

```json
"version": "25.9.13.36"
```
