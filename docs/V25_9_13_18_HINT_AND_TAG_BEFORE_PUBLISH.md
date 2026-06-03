# v25.9.13.18 - Hint + Tag Before Publish

## Mục tiêu

Sửa luồng export sang Open edX Library để tránh component đã publish nhưng vẫn hiện `Unpublished changes` do tag được gắn sau publish.

## Thay đổi chính

- OLX problem có thêm `<demandhint><hint>...</hint></demandhint>`.
- Hint không lấy từ explanation để tránh lộ đáp án. Hint chỉ hướng người học về mục tiêu/chapter/source liên quan.
- Connector CMS đổi thứ tự import:
  1. create/update problem block draft
  2. set OLX
  3. gắn Open edX Content Tags
  4. publish draft
- Giữ direct publish path cho Ulmo để tránh lỗi `PublishLog.DoesNotExist`.

## File sửa

- `backend/app/services/openedx_exporter.py`
- `openedx-connector-plugin/openedx_ai_connector/views.py`

## Cách cập nhật

Nếu chỉ muốn lấy plugin mới, copy `openedx-connector-plugin/openedx_ai_connector/views.py` vào CMS và restart:

```bash
tutor local restart cms cms-worker
```

Vì có sửa exporter backend để thêm hint, nên AI Server cũng cần build lại nếu muốn OLX mới có hint:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```
