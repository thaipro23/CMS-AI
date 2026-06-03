# v25.9.13.40 - Production Security Hardening

Bản này khóa các điểm rủi ro production trước khi triển khai AI Server/Open edX thật.

## Backend

- Thêm production fail-fast validation cho `APP_ENV=production`. Backend sẽ không boot nếu còn `DEBUG=true`, `AUTO_CREATE_TABLES=true`, `AUTH_MODE=demo`, `ALLOW_DEMO_ROLE_HEADER=true`, `USE_MOCK_OPENEDX=true`, `MOCK_LLM=true`, wildcard CORS, JWT secret yếu, thiếu metrics token hoặc thiếu connector HMAC secret.
- Thêm `CORS_ALLOWED_ORIGINS` whitelist, bỏ `allow_origins=["*"]`.
- Bảo vệ `/metrics` bằng `METRICS_TOKEN` qua `X-Metrics-Token` hoặc `Authorization: Bearer`.
- Runtime settings không còn persist secret vào `runtime-settings.json`; các secret như OpenAI API key, Open edX client secret/access token và JWT secret chỉ lấy từ env/secret manager.
- JWT/SSO hỗ trợ đọc token từ HttpOnly cookie `ai_openedx_access_token` hoặc `access_token`.
- Production non-admin không có `course_ids`/`courses` claim sẽ bị deny thay vì xem toàn bộ khóa học.

## Open edX connector

- Thêm HMAC server-to-server header cho request từ AI Server tới CMS connector.
- Plugin yêu cầu HMAC hợp lệ hoặc Studio staff/admin cho `studio-content`, diagnostics, publish, verify, delete/rollback và backfill tags.
- Bỏ fallback tự lấy first active staff user. Production bắt buộc cấu hình `AI_CONNECTOR_PUBLISH_USERNAME` nếu request vào dưới dạng AnonymousUser.
- Anonymous publish/rollback bị chặn.
- Asset/transcript download có SSRF guard: allowlist host, block private/internal host ngoài allowlist, disable redirect, chỉ forward cookie cho cùng host.

## Frontend

- Bearer token nhập tay chỉ giữ trong memory, không lưu localStorage. Production nên dùng HttpOnly Secure SameSite cookie từ auth/reverse proxy.

## Env mới

- `.env.production.example`
- `CORS_ALLOWED_ORIGINS`
- `METRICS_TOKEN`
- `OPENEDX_CONNECTOR_HMAC_SECRET` / `AI_CONNECTOR_HMAC_SECRET`
- `OPENEDX_ALLOWED_DOWNLOAD_HOSTS` / `AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS`
- `REQUIRE_COURSE_SCOPE_IN_PRODUCTION`
