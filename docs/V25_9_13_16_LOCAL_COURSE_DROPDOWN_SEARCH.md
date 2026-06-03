# v25.9.13.16 - Local Course Dropdown Search

Mục tiêu: sửa `/sync` để không gọi API search mỗi lần gõ. Frontend tải tối đa 1000 khóa học đã sync một lần, sau đó tìm kiếm cục bộ ngay trong dropdown.

## Thay đổi chính

- `/sync` gọi `GET /api/courses?limit=1000` để lấy danh sách khóa học đã sync.
- Ô tìm trong dropdown chỉ lọc trên mảng `syncedCourses` ở frontend, không gọi lại `GET /api/courses?search=...` mỗi lần nhập.
- Nút `Tải lại` trong dropdown chỉ reload lại toàn bộ danh sách đã sync.
- Giữ ô nhập mã khóa học riêng để đồng bộ course mới/chưa có trong danh sách.

## File sửa

- `frontend/app/sync/page.tsx`
- `frontend/package.json`
- `backend/app/core/config.py`
- `.env.example`

## Test

Backend compile:

```bash
python -m compileall -q backend/app
```
