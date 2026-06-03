# v25.9.13.48 - CMS session bridge SSO

Mục tiêu: người dùng đã đăng nhập CMS/Studio Open edX có thể mở AI Server mà không phải nhập lại mật khẩu hoặc tự dán JWT.

## Luồng đăng nhập

1. Frontend AI redirect trình duyệt tới CMS:
   `/api/ai-connector/v1/session/bridge?return_to=<AI_CALLBACK>&course_id=<COURSE_ID>`
2. CMS dùng session cookie hiện tại của Open edX. Nếu chưa đăng nhập, CMS hiện trang login như bình thường.
3. Plugin CMS ký một ticket ngắn hạn bằng `AI_CONNECTOR_SESSION_BRIDGE_SECRET` hoặc fallback `AI_CONNECTOR_HMAC_SECRET`.
4. Trình duyệt quay lại AI frontend `/auth/cms-callback?ticket=...`.
5. AI frontend gọi backend `POST /api/auth/openedx-session/exchange`.
6. AI backend xác thực ticket bằng `OPENEDX_SESSION_BRIDGE_SECRET` hoặc fallback `OPENEDX_CONNECTOR_HMAC_SECRET`, rồi cấp JWT ngắn hạn cho AI Server.

## Env AI Server

```env
AUTH_MODE=openedx_sso
ALLOW_DEMO_ROLE_HEADER=false
JWT_SECRET=<strong secret>
OPENEDX_CONNECTOR_HMAC_SECRET=<shared secret>
OPENEDX_SESSION_BRIDGE_SECRET=
AUTH_COOKIE_SECURE=false # local http only; production https should be true
AUTH_COOKIE_SAMESITE=lax
AUTH_SESSION_TOKEN_TTL_SECONDS=28800
NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://scms-test.poly.edu.vn
```

Nếu `OPENEDX_SESSION_BRIDGE_SECRET` để trống, backend dùng `OPENEDX_CONNECTOR_HMAC_SECRET`.

## Env CMS/Studio connector

Thêm vào `cms` và `cms-worker`:

```yaml
AI_CONNECTOR_HMAC_SECRET: "<same shared secret>"
AI_CONNECTOR_SESSION_BRIDGE_ALLOWED_RETURN_HOSTS: "localhost,127.0.0.1,ai.cms-test.poly.edu.vn"
```

Nếu `AI_CONNECTOR_SESSION_BRIDGE_SECRET` không set, plugin dùng `AI_CONNECTOR_HMAC_SECRET`.

## Lưu ý local sethost

Với AI Server chạy local `http://localhost:3000`, bấm nút **Dùng phiên CMS** trong sidebar. Đây là top-level redirect nên hoạt động tốt hơn XHR cross-site, tránh bị SameSite cookie chặn.

## Quyền

- CMS `is_staff` hoặc `is_superuser` được map thành AI `admin`.
- User có quyền author course được map thành `teacher` cho `course_id` đang yêu cầu.
- User không có quyền author course được map thành `viewer`.
