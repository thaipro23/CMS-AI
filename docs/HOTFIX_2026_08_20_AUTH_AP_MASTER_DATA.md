# Hotfix 2026-08-20 — CMS auth và AP master data

## Nội dung sửa

- Callback đăng nhập CMS chờ `GET /api/rbac/me` xác nhận quyền thành công rồi mới chuyển về trang đích.
- Mỗi lần kiểm tra quyền có sequence guard; phản hồi 401 cũ không thể ghi đè phiên vừa exchange.
- Danh sách môn lấy từ `https://api_v2.poly.edu.vn/get-course` với:
  - `branch=poly` cố định cho bước tìm môn.
  - `term_name` là kỳ người dùng chọn, ví dụ `Summer 2026`.
  - Không gửi campus khi lấy danh sách môn.
- Danh mục cơ sở chỉ nhập/sửa thủ công tại `/premises`.
- Hai endpoint cũ `/academic/campuses/seed-from-env` và `/academic/campuses/sync-from-ap` trả `410 ACADEMIC_CAMPUS_MANUAL_ONLY`.
- Runtime, env mẫu và Docker Compose không còn tham chiếu `apitest.poly.edu.vn`.

## Cấu hình AP chuẩn

```env
ACADEMIC_AP_API_BASE_URL=https://api_v2.poly.edu.vn
ACADEMIC_AP_GET_COURSE_ENDPOINT=/get-course
ACADEMIC_AP_GET_COURSE_FILE_CACHE_ENABLED=true
ACADEMIC_AP_GET_COURSE_FILE_CACHE_DIR=/tmp/ai-server-ap-cache/get-course
ACADEMIC_AP_GET_COURSE_FILE_CACHE_TTL_SECONDS=86400
ACADEMIC_AP_GET_COURSE_FILE_CACHE_REFRESH=false
ACADEMIC_AP_TLS_MODE=off
ACADEMIC_AP_API_KEY=<Kubernetes Secret/Jenkins credential>
```

`ACADEMIC_AP_API_KEY` là bắt buộc cho cả `/get-course` và `/get-data-cms`; backend gửi key bằng header `Authorization: Bearer ...`.
`api_v2.poly.edu.vn` hiện có certificate hostname mismatch nên client tắt TLS verification riêng cho host này (`verify=False`). Không áp dụng ngoại lệ này cho các host AP khác.

## Kiểm tra sau triển khai

1. Mở AI Server từ một phiên CMS hợp lệ và xác nhận vào được ngay, không cần F5.
2. Mở Network và xác nhận request `/api/rbac/me` cuối cùng trả 200 trước khi trang đích hiển thị.
3. Tại `/premises`, nhập thủ công tối thiểu một cơ sở cho từng hệ cần đồng bộ.
4. Tại `/ap-sync`, chọn `Summer 2026`, chạy chế độ “Chỉ kiểm tra kế hoạch”.
5. Xác nhận plan ghi `ap_subject_endpoint=/get-course?branch=poly&term_name=<selected-term>` và `campus_source=manual.academic_campuses`.

## Kiểm thử đã chạy

- Python compile và Ruff: đạt.
- 20 kiểm thử hồi quy liên quan auth/AP/cơ sở: đạt.
- Frontend TypeScript, ESLint và Next.js production build: đạt.
