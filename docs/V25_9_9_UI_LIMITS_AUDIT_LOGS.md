# v25.9.9 - Vietnamese UI, Course Limits & Audit Logs

## Điểm mới

- Tối ưu giao diện điều hướng chính sang tiếng Việt và bỏ khối note thừa ở sidebar.
- Thêm trang `/audit` để xem nhật ký hệ thống.
- Thêm API và UI cấu hình giới hạn tạo câu hỏi theo từng khóa học:
  - Tổng số câu tối đa trong một khóa học.
  - Số câu tối đa trong mỗi lượt tạo.
  - Ngân sách tháng và số lần retry tối đa.
- Các thao tác quan trọng ghi audit log:
  - Đồng bộ học liệu.
  - Ước tính chi phí.
  - Tạo job generate.
  - Hard stop/quota/budget block.
  - Cập nhật settings.
  - Test GPT.
  - Test Open edX.
  - Cập nhật giới hạn khóa học.

## Phân loại lỗi trong audit log

- `user`: lỗi do người dùng/cấu hình/quyền/quota.
- `system`: lỗi do backend/parser/database/service nội bộ.
- `external`: lỗi do OpenAI/Open edX/network/rate limit.

## API mới

```txt
GET /api/cost/policy?course_id=...
PATCH /api/cost/policy
GET /api/audit?course_id=...&status=...&error_type=...&actor_id=...&page=1&page_size=20
```

## Chạy lại

```bat
docker compose down
docker compose up --build
```

Nếu DB cũ thiếu bảng mới:

```bat
docker compose down -v
docker compose up --build
```
