# v25.9.13.13 - Sync Course Picker + Compact Sync Header

## Mục tiêu

Trang `/sync` bỏ phần header lớn để rộng màn hình hơn và thêm khu vực chọn khóa học trực tiếp trên trang đồng bộ.

## Thay đổi chính

- Ẩn topbar/header chung khi đang ở `/sync`.
- Bỏ hero header lớn của trang Sync.
- Thêm ô nhập mã khóa học để đồng bộ trực tiếp, ví dụ `course-v1:FPT+DBI102+su26`.
- Thêm ô tìm khóa học đã sync.
- Thêm dropdown chọn khóa học đang hiển thị.
- Thêm endpoint `GET /api/courses?search=&limit=` để lấy danh sách khóa học AI Server đã sync/index.
- Sau khi đồng bộ xong, danh sách khóa học được tải lại tự động.

## File sửa

- `frontend/components/layout/AppShell.tsx`
- `frontend/app/sync/page.tsx`
- `frontend/app/globals.css`
- `frontend/lib/api.ts`
- `frontend/types/index.ts`
- `backend/app/api/routes/courses.py`
- `backend/app/schemas/course.py`
- `backend/app/core/config.py`
- `.env.example`
- `frontend/package.json`

## Endpoint mới

```http
GET /api/courses?search=DBI102&limit=50
```

Response:

```json
[
  {
    "course_id": "course-v1:FPT+DBI102+su26",
    "title": "DBI102",
    "node_count": 120,
    "chunk_count": 45,
    "token_count": 18000,
    "last_synced_at": "2026-05-28T..."
  }
]
```

## Cách chạy

Vì bản này sửa frontend và backend AI Server, cần build lại AI Server:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

Không cần build lại Open edX nếu bạn chỉ dùng thay đổi UI/endpoint này.
