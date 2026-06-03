# v25.9.13.15 - Global Header Removal + Searchable Course Dropdown

## Mục tiêu

- Bỏ header/topbar lớn khỏi toàn bộ trang frontend.
- Sửa UI `/sync` không bị vỡ khi có nhiều nút và course id dài.
- Gộp ô tìm kiếm khóa học vào dropdown chọn khóa học.
- Danh sách khóa học đã sync lấy tối đa 1000 khóa học.

## Thay đổi chính

### Frontend

- `components/layout/AppShell.tsx`
  - Không render topbar lớn ở mọi trang.
  - Main content dùng compact shell toàn chiều rộng.

- `app/sync/page.tsx`
  - Bỏ ô tìm kiếm riêng bên ngoài.
  - Thêm searchable combobox cho khóa học đã sync.
  - Nút đồng bộ nằm cùng ô nhập mã khóa học.
  - Nút xóa & đồng bộ lại rút gọn để tránh vỡ UI.

- `app/globals.css`
  - Thêm style combobox khóa học.
  - Sửa content shell full width.
  - Sửa layout control card responsive.

### Backend

- `GET /api/courses`
  - `limit` tăng từ 200 lên 1000.
  - Default limit = 1000.

## Cách chạy

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

Không cần build lại Open edX/CMS.
