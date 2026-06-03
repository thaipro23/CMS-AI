# v23 Admin Settings

Bản này bổ sung trang `/settings` chỉ dành cho admin.

## Quyền truy cập

- Frontend ẩn menu Settings nếu role không có quyền `manage_settings`.
- Trang `/settings` tự chặn teacher/reviewer/viewer.
- Backend chặn thật bằng `require_permission('manage_settings')` tại:
  - `GET /api/settings/runtime`
  - `PATCH /api/settings/runtime`

## Cấu hình chỉnh được

### Model Gateway

- `MODEL_PROVIDER`: `openai`, `local`, `auto`
- `OPENAI_MODEL`, mặc định `gpt-5-mini`
- `MOCK_LLM`: bật/tắt mock LLM
- `OPENAI_API_KEY`: để trống khi lưu nếu muốn giữ key cũ

### Open edX Connector

- `USE_MOCK_OPENEDX`: bật/tắt mock Open edX
- `OPENEDX_BASE_URL`
- `OPENEDX_CLIENT_ID`
- `OPENEDX_CLIENT_SECRET`
- `OPENEDX_ACCESS_TOKEN`
- `OPENEDX_OAUTH_TOKEN_URL`
- `OPENEDX_COURSE_BLOCKS_PATH`
- `OPENEDX_PUBLISH_ENDPOINT`

### SSO/Auth

- `AUTH_MODE`: `demo`, `jwt`, `openedx_sso`
- `ALLOW_DEMO_ROLE_HEADER`
- `JWT_SECRET`

## Lưu ý bảo mật

Secret/API key không trả plaintext về frontend. API chỉ trả trạng thái `has_*` và giá trị mask. Khi PATCH, secret để trống nghĩa là giữ giá trị cũ.

Trong demo/dev, cấu hình runtime được lưu tại `RUNTIME_CONFIG_PATH`, mặc định `/app/.runtime/runtime-settings.json`, được backend và worker dùng chung qua volume `/app`. Production nên dùng biến môi trường hoặc secret manager thay vì sửa trực tiếp trong UI.
