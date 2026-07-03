# v25.9.15.6.31.12 — Security Hotfix

Nền: `v25.9.15.6.31.11-remove-dark-landing-bank-dashboard-redesign`.

## Đã sửa

- Open edX `is_staff` không còn được map thành AI `admin`. Chỉ `is_superuser` hoặc group cấu hình `AI_CONNECTOR_ADMIN_GROUPS` mới là admin AI.
- Fallback khi lỗi import quyền course author đã fail-closed: staff không tự thành teacher/admin khi import Open edX internal API lỗi.
- Các endpoint `csrf_exempt` của connector dùng cho publish/rollback/quiz/itembank/diagnostics chuyển sang HMAC-only; staff browser cookie không còn được chấp nhận ở các endpoint server-to-server này.
- Session bridge không tự allow `localhost/127.0.0.1` khi `DEBUG=false`; production phải cấu hình `AI_CONNECTOR_SESSION_BRIDGE_ALLOWED_RETURN_HOSTS`.
- Backend AI JWT bắt buộc `iss`, `aud`, `exp`, `sub`, `token_type=ai_session`.
- Backend AI không còn đọc cookie generic `access_token`, chỉ đọc `ai_openedx_access_token`.
- Thêm Origin/Referer guard cho request mutating API trong production khi dùng cookie auth. Origin lạ bị 403.
- Connector production không trả traceback/module/repr ra response nếu `AI_CONNECTOR_DEBUG_ERRORS=false`.
- Unit reset `quiz-config/upsert` chuyển sang HMAC-only.
- Runtime quiz timer JS validate `event.origin` và postMessage trả về đúng `event.origin`, không dùng `*`.
- Frontend production không gửi fallback `X-User-Role` / `X-User-Id` nếu chưa có token.

## Env mới/cần kiểm tra

```env
APP_VERSION=25.9.15.6.31.12-security-hotfix
JWT_ISSUER=ai-learning-server
JWT_AUDIENCE=ai-learning-server-api
NEXT_PUBLIC_APP_ENV=production
AI_CONNECTOR_SESSION_BRIDGE_ALLOWED_RETURN_HOSTS=ai.cms-test.poly.edu.vn
AI_CONNECTOR_DEBUG_ERRORS=false
AI_QUIZ_RUNTIME_ALLOWED_ORIGINS=https://app.cms-test.poly.edu.vn,https://cms-test.poly.edu.vn,https://scms-test.poly.edu.vn
```

## Deploy nhanh

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.15.6.31.12-security-hotfix.zip -d /opt/ai-server.new
# copy .env.production hiện tại sang thư mục mới rồi cập nhật env ở trên

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker
```

## Check nhanh

```bash
# Backend không nhận cookie generic access_token nữa
grep -R "cookies.get('access_token')" -n backend/app || true

# Connector write endpoints phải HMAC-only
grep -n "def _require_connector_write" openedx-connector-plugin/openedx_ai_connector/views.py

# Timer upsert phải HMAC-only
grep -n "def quiz_timer_config_upsert" openedx-unit-reset-plugin/openedx_unit_reset/views.py
```
