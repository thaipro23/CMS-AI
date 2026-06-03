# v25.9.13.49 - Auto CMS Session Login

Mục tiêu: nếu user đã đăng nhập CMS/Studio Open edX thì khi mở AI Server, frontend tự chuyển qua CMS session bridge và nhận phiên AI, không cần bấm nút hoặc dán JWT.

## Thay đổi chính

- Frontend tự gọi CMS session bridge khi chưa có AI session.
- Callback `/auth/cms-callback` đổi CMS ticket sang AI JWT như v25.9.13.48.
- AI session token ngắn hạn được giữ trong `sessionStorage`, không lưu `localStorage`.
- Có thể tắt auto-login bằng `NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=false`.

## Yêu cầu cấu hình

AI Server `.env.production`:

```env
AUTH_MODE=openedx_sso
NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://scms-test.poly.edu.vn
NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true
OPENEDX_CONNECTOR_HMAC_SECRET=<same-as-cms>
AUTH_COOKIE_SECURE=false # local HTTP only
```

Open edX CMS container:

```env
AI_CONNECTOR_HMAC_SECRET=<same-as-ai-server>
AI_CONNECTOR_SESSION_BRIDGE_ALLOWED_RETURN_HOSTS=localhost,127.0.0.1,ai.cms-test.poly.edu.vn
```

Nếu chạy AI Server local bằng `http://localhost:3000`, bắt buộc thêm `localhost,127.0.0.1` vào allowed return hosts.
