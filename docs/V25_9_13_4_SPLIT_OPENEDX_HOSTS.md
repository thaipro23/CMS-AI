# v25.9.13.4 - Split Open edX CMS/LMS/OAuth Hosts

## Lý do

Tutor/Open edX local thường tách host:

- LMS: `http://local.openedx.io`
- CMS/Studio: `http://studio.local.openedx.io`

Connector Studio dùng để sync draft content và publish Library/Problem nằm ở CMS/Studio. Nhưng OAuth token endpoint `/oauth2/access_token/` thường nằm ở LMS. Nếu dùng chung `OPENEDX_BASE_URL=http://studio.local.openedx.io`, backend sẽ gọi `http://studio.local.openedx.io/oauth2/access_token/` và có thể bị `404 Not Found`.

## Env mới

```env
# Alias cũ, vẫn giữ để tương thích. Nên để bằng CMS/Studio.
OPENEDX_BASE_URL=http://studio.local.openedx.io

# Host CMS/Studio: connector endpoints, draft content, publish Library/Problem.
OPENEDX_CMS_BASE_URL=http://studio.local.openedx.io

# Host LMS: Course Blocks API fallback.
OPENEDX_LMS_BASE_URL=http://local.openedx.io

# Host OAuth: client_credentials token endpoint. Tutor local thường dùng LMS.
OPENEDX_OAUTH_BASE_URL=http://local.openedx.io
OPENEDX_OAUTH_TOKEN_URL=/oauth2/access_token/
```

## Mapping sử dụng

- `_get_studio_content`, `ensure_problem_library`, `import_problem_to_library`, `publish_problem_olx` dùng `OPENEDX_CMS_BASE_URL`.
- `_get_token` dùng `OPENEDX_OAUTH_BASE_URL`.
- `_get_course_blocks_api` fallback dùng `OPENEDX_LMS_BASE_URL`.

## Test nhanh

```bash
curl -I http://local.openedx.io/oauth2/access_token/
curl -I http://studio.local.openedx.io/api/ai-connector/v1/health
```

Sau đó build lại AI Server:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```
