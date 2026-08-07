# Báo cáo sửa lỗi Batch 35.2

## Lỗi gốc

API `/api/academic/subject-deliveries` trả HTTP 500 vì PostgreSQL `GroupingError`. SQLAlchemy sinh hai bind parameter khác nhau cho biểu thức `lower(coalesce(academic_classes.branch, ''))`, làm biểu thức SELECT và GROUP BY không được PostgreSQL xem là giống nhau.

## Cách sửa

- Dùng một `class_branch_key` duy nhất và `literal_column("''")`.
- Bổ sung chế độ API `management_scope=term` để tổng hợp delivery theo môn + học kỳ + hệ.
- Màn Quản lý môn học bỏ Block selector.
- Chọn CMS/Udemy/Bỏ chọn cập nhật tất cả Block delivery của môn.
- Các chức năng kế hoạch, tiến độ, import, lớp và CMS vẫn theo Block.
- Kỳ mới kế thừa lựa chọn nhất quán của kỳ gần nhất; mixed hoặc chưa chọn thì để trống.
- Không có migration và không chuyển dữ liệu ACMS.

## Kiểm tra

- Regression Batch 31–35.2: đạt.
- Response model: đạt.
- Carry-forward nhất quán: đạt.
- Không carry-forward trạng thái mixed: đạt.
- TypeScript syntax và Python compile: đạt.
