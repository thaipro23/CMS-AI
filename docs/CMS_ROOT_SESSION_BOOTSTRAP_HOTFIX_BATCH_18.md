# CMS Root Session Bootstrap Hotfix — Batch 18

## Hiện tượng

Khi truy cập trực tiếp `http://ai.cms-test.poly.edu.vn`, Next.js chuyển ngay sang `/bank` nhưng không luôn khởi động CMS session bridge. Khi người dùng mở một route khác, AppShell mới chạy lại luồng kiểm tra và chuyển sang CMS để nhận phiên.

## Nguyên nhân

1. Route `/` dùng server-side `redirect('/bank')`, nên không có một client entry state rõ ràng để chờ `AppProvider` xác minh cookie AI và khởi động CMS bridge.
2. AppShell chặn bridge bằng khóa thời gian trong `sessionStorage` trong 30 giây. Khóa có thể còn lại từ một lần điều hướng CMS bị hủy, reload giữa chừng hoặc callback lỗi. Khi đó lần vào `/bank` đầu tiên bị bỏ qua hoàn toàn.
3. Callback luôn quay về `/bank`, không ghi nhớ route người dùng thực sự muốn mở.

## Thay đổi

### Root route

- Bỏ server redirect tức thời.
- `/` trở thành client bootstrap page.
- Khi AI session hợp lệ, chuyển sang `/bank`.
- Khi chưa có session, AppShell khởi động CMS bridge ngay trên root route.

### AppShell CMS bridge

- Bỏ điều kiện khóa 30 giây bằng `sessionStorage`.
- Dùng `useRef` để chỉ chặn effect trùng trong cùng một client render.
- Mỗi page load mới vẫn có thể khởi động SSO ngay.
- Dùng `window.location.replace` để không để lại trang chưa xác thực trong browser history.
- `/` được chuẩn hóa có return path là `/bank`.

### Return path

- Lưu route nội bộ người dùng muốn mở vào `sessionStorage`.
- Gắn `next` vào callback URL.
- Sau khi exchange ticket thành công, callback quay lại đúng route yêu cầu.
- Return path được validate: chỉ chấp nhận path nội bộ bắt đầu bằng `/`, từ chối `//...` và `/auth/...` để tránh open redirect/loop.

### Callback recovery

- Xóa marker bridge khi callback thiếu ticket, exchange thất bại hoặc thành công.
- Marker cũ không còn làm kẹt lần đăng nhập tiếp theo.

## File thay đổi

- `frontend/app/page.tsx`
- `frontend/components/layout/AppShell.tsx`
- `frontend/app/auth/cms-callback/page.tsx`
- `frontend/lib/api.ts`

## Behavior mong đợi

```text
Truy cập /
→ AppProvider gọi /api/rbac/me
→ Có AI cookie: vào /bank
→ Không có AI cookie: chuyển ngay sang CMS session bridge
→ CMS dùng phiên Studio hiện tại hoặc yêu cầu đăng nhập
→ callback exchange ticket
→ quay lại /bank
```

Với deep link:

```text
Truy cập /student-management/classes/{id}
→ chưa có AI session
→ CMS bridge
→ callback
→ quay lại đúng /student-management/classes/{id}?...
```

## Verification

Không chạy TypeScript check, lint, build hoặc browser test theo yêu cầu của người dùng. Cần xác minh sau deploy trên UAT với cookie CMS thật.
