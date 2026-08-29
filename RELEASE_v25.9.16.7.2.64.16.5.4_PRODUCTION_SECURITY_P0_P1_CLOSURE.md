# v25.9.16.7.2.64.16.5.4 — Production Security P0/P1 Closure

## Mục tiêu

Bản này ưu tiên đóng các phát hiện P0/P1 trước production, tiếp tục trực tiếp từ `.64.16.5.3`. Không thay Bank hierarchy, Open edX publish semantics, AP sync, Analytics hoặc Assignment externalization.

## 1. Bank diff preview không còn mutation

- `BankVersionDiffPreviewRequest.persist` mặc định `false`.
- `POST /bank-versions/{id}/diff/preview` luôn chạy `persist=False` và chỉ cần quyền xem đúng scope.
- Tách thao tác lưu thành `POST /bank-versions/{id}/diffs`.
- Endpoint lưu yêu cầu `edit_questions` và business permission `question.edit`.
- Diff lưu dùng SHA-256 idempotency key theo hai version, material hashes và concept changes.
- Unique constraint DB ngăn tạo trùng; service xử lý cả race đồng thời bằng `IntegrityError` rồi tái sử dụng row đã tồn tại.

## 2. SSO production cookie-only

- Response exchange production không trả JWT cho JavaScript.
- Frontend production không giữ hoặc gửi Bearer token; mọi API dùng cookie HttpOnly với `credentials: include`.
- CMS bridge ticket có `jti`, tuổi tối đa 30–60 giây và chỉ dùng một lần qua Redis `SET NX`.
- Exchange giới hạn theo IP và fingerprint ticket.
- AI JWT có `jti`, TTL production 15 phút–2 giờ.
- Thêm `/auth/logout`, revoke `jti` trong Redis và xóa cookie.
- User menu có thao tác `Đăng xuất`; trang `/auth/logged-out` không tự khởi động lại SSO cho đến khi người dùng chọn đăng nhập lại.

## 3. Chuẩn hóa lỗi công khai

- Không còn `HTTPException(detail=str(exc))` trong API routes.
- Exception thật chỉ ghi server log với `logger.exception`.
- Client nhận mã lỗi/message ổn định, không nhận tên bảng, constraint, URL nội bộ hoặc traceback.
- Middleware tạo/duy trì request ID và trả `X-Request-ID`.

## 4. Frontend contract nhỏ nhưng cần thiết

- URL table state chấp nhận `10/20/50/100` dòng mỗi trang.
- `EnterpriseDataTable.defaultVisible` được thực thi thật.
- Column menu có `Hiện tất cả` và `Mặc định`.

## 5. Migration

Migration mới có chủ đích:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

Chain:

```text
0052_v25_9_16_7_2_27
→ 0053_v25_9_16_7_2_64_16_5_4
```

Migration thêm `idempotency_key` nullable và unique constraint cho `ai_bank_version_diffs`.

## 6. Gate mới

```bash
./scripts/production-security-closure-report.sh
```

Gate kiểm tra 15 contract: preview read-only, persist permission, idempotency/migration, cookie-only SSO, ticket một lần, revocation, rate-limit, logout, frontend không dùng production Bearer và không lộ exception.

## Boundary

Bản này chưa xử lý các hạng mục lớn tiếp theo: export bất đồng bộ, chia Celery queues, API timeout/cancellation, CI/E2E, Docker non-root và tách god files. Những phần đó được đưa vào roadmap kế tiếp.
