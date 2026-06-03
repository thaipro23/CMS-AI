# v25.9.12.1 - CMS Studio Connector URL Route Fix

## Mục tiêu

Bản này sửa lỗi plugin Studio connector đã cài được vào container LMS/CMS nhưng endpoint `/api/ai-connector/v1/health` vẫn trả `404 Not Found`.

## Nguyên nhân

`apps.py` đã mount plugin dưới prefix:

```text
/api/ai-connector/v1/
```

nhưng `openedx_ai_connector/urls.py` lại khai báo lặp lại prefix `api/ai-connector/v1/...`, khiến URL thật bị nhân đôi prefix:

```text
/api/ai-connector/v1/api/ai-connector/v1/...
```

Ngoài ra plugin chưa có route `health`, nên không có endpoint đơn giản để kiểm tra plugin đã chạy.

## Đã sửa

- `openedx-connector-plugin/setup.py`
  - thêm `entry_points` cho `lms.djangoapp` và `cms.djangoapp`
  - nâng plugin package lên `0.1.1`
- `openedx-connector-plugin/openedx_ai_connector/apps.py`
  - khai báo `plugin_app.url_config` cho LMS và CMS
  - mount URL prefix `^api/ai-connector/v1/`
- `openedx-connector-plugin/openedx_ai_connector/urls.py`
  - chuyển toàn bộ path về dạng relative
  - thêm `health` và `health/`
- `openedx-connector-plugin/openedx_ai_connector/views.py`
  - thêm hàm `health()` trả JSON đơn giản

## Cách cài nhanh khi đang mount `E:\FPL\openedx-platform`

```bat
docker exec -it tutor_local-cms-1 bash -lc "/openedx/venv/bin/pip uninstall -y openedx-ai-connector && /openedx/venv/bin/pip install -e /openedx/edx-platform/openedx-connector-plugin"
docker exec -it tutor_local-lms-1 bash -lc "/openedx/venv/bin/pip uninstall -y openedx-ai-connector && /openedx/venv/bin/pip install -e /openedx/edx-platform/openedx-connector-plugin"
docker restart tutor_local-lms-1 tutor_local-cms-1 tutor_local-lms-worker-1 tutor_local-cms-worker-1
```

## Test

```bat
curl -i http://studio.local.openedx.io/api/ai-connector/v1/health
curl -i http://local.openedx.io/api/ai-connector/v1/health
curl -i http://studio.local.openedx.io/api/ai-connector/v1/courses/course-v1:FPT+DBI102+su26/studio-content
```

Kỳ vọng `/health` trả:

```json
{"status":"ok","service":"openedx_ai_connector","message":"AI connector is running"}
```
