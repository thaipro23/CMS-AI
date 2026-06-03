# v24.6 - Security RBAC + Mobile UI Hotfix

## Mục tiêu

Bản v24.5 có endpoint xóa câu hỏi dạng:

```http
DELETE /api/question-bank/{question_id}?actor=teacher
```

Cách này không an toàn vì `actor` là dữ liệu client tự gửi. Người dùng có thể sửa query string hoặc gọi trực tiếp API bằng curl/Postman.

Bản v24.6 sửa theo nguyên tắc production:

- Không tin `actor`, `role`, `user_id` từ query/body cho hành động nhạy cảm.
- Backend lấy actor từ authenticated principal.
- `DELETE` không nhận `actor` ở query string nữa.
- Có permission riêng `delete_questions`.
- Có course-level access check dựa trên `course_ids/courses` trong JWT.
- Production không cho dùng demo header auth.
- Mobile UI được chỉnh để không vỡ layout trên điện thoại.

## Endpoint DELETE mới

```http
DELETE /api/question-bank/{question_id}
Authorization: Bearer <jwt>
```

Dev demo vẫn có thể dùng:

```http
DELETE /api/question-bank/{question_id}
X-User-Role: teacher
X-User-Id: demo-teacher
```

Nhưng demo header chỉ dành cho local/dev. Nếu `APP_ENV=production` mà vẫn dùng `AUTH_MODE=demo`, backend sẽ báo lỗi cấu hình.

## Quyền xóa

Permission mới:

```txt
delete_questions
```

Mặc định:

```txt
admin: có delete_questions
teacher: có delete_questions
reviewer: không có delete_questions
viewer: không có delete_questions
```

Quy tắc nghiệp vụ giữ nguyên:

```txt
pending_review / approved / rejected / draft_error: xóa được
published: không cho xóa trực tiếp
```

Published question không xóa local trực tiếp vì có thể đã import sang Open edX Library.

## Auth mode

### Dev/demo

```env
APP_ENV=dev
AUTH_MODE=demo
ALLOW_DEMO_ROLE_HEADER=true
```

Frontend gửi:

```txt
X-User-Role
X-User-Id
```

### Production JWT/SSO

```env
APP_ENV=production
AUTH_MODE=jwt
JWT_SECRET=change_me_to_real_secret
ALLOW_DEMO_ROLE_HEADER=false
```

Frontend hoặc Open edX SSO proxy gửi:

```http
Authorization: Bearer <jwt>
```

JWT nên có claim:

```json
{
  "sub": "teacher01",
  "email": "teacher01@fpt.edu.vn",
  "role": "teacher",
  "course_ids": ["course-v1:FPT+DOM1051+2026"]
}
```

Nếu token có `course_ids`, backend sẽ chặn truy cập course khác.

## API đã đổi actor sang server-side

Các action sau không còn tin actor client:

- edit question
- delete question
- approve/reject/change status
- bulk approve
- publish to Open edX
- generate question job requested_by

`actor` được lấy từ `user.user_id` sau khi auth.

## Mobile UI fix

Đã chỉnh CSS responsive:

- Sidebar chuyển thành thanh nav ngang cuộn được.
- Topbar không sticky/fixed gây che nội dung mobile.
- Form controls co xuống 1 cột.
- Question card co thành 1 cột.
- Action buttons trong question card tự wrap 2 cột hoặc 1 cột trên màn hình nhỏ.
- Input font-size 16px ở màn hình rất nhỏ để tránh iOS auto zoom.

