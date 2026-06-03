# v25.9.12.10 - Clean Resync + Token Total Fix

## Mục tiêu
Sửa 2 vấn đề trên trang `/sync`:

1. Nút **Tải lại** ở header chỉ gọi lại dữ liệu UI nên dễ gây hiểu nhầm là đang đồng bộ lại khóa học. Bản này thay bằng nút **Xóa dữ liệu & đồng bộ lại** có xác nhận.
2. Metric **Tokens** đang tính theo các chunk đang hiển thị ở trang hiện tại, nên có thể hiện 18k trong khi node gốc là 122k tokens. Bản này trả thêm `total_tokens` từ backend cho toàn bộ kết quả theo filter.

## Thay đổi backend

### Endpoint mới

```http
POST /api/courses/{course_id}/clean-resync?confirm=RESET_COURSE_SYNC
```

Endpoint này xóa dữ liệu học liệu đã sync trong AI Server rồi đồng bộ lại từ CMS/Studio:

- `ai_content_chunks`
- `ai_course_sync_state`
- `ai_topics` cũ/deprecated

Không xóa:

- câu hỏi đã generate trong Question Bank
- jobs lịch sử
- Open edX Studio/CMS content thật

### Chunk pagination

`GET /api/courses/{course_id}/chunks/page` trả thêm:

```json
{
  "total_tokens": 122073
}
```

Giá trị này là tổng token của toàn bộ query/filter hiện tại, không phải token của trang hiện tại.

## Thay đổi frontend

Header `/sync` đổi nút **Tải lại** thành **Xóa dữ liệu & đồng bộ lại**. Khi bấm sẽ mở modal xác nhận và bắt nhập:

```txt
RESET_COURSE_SYNC
```

Metric **Tokens** dùng `total_tokens` nên đồng bộ với token aggregate của node/course.
