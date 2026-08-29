# UX/UI context v25.9.16.7.2.20

## Student Management

Trang `/student-management` giờ có hành động cấp bộ lọc:

- **Auto map tất cả**: chạy theo Hệ + Học kỳ + Cơ sở + Trạng thái + Từ khóa hiện tại.
- Hệ thống chỉ map các môn tìm thấy đúng một Course CMS an toàn.
- Các môn đã map hoặc vừa map xong sẽ đưa lớp vào hàng đợi full CMS sync.
- Full CMS sync xử lý user CMS, enroll và dữ liệu học tập qua job nền, không khóa UI lâu.

## Class Detail

Trang `/student-management/classes/{class_id}` có nút **Hành vi học** đặt cạnh các thao tác đồng bộ.

Nút này mở `/analytics/learning` với đủ context lớp, giúp giáo viên vào thẳng kết quả hành vi học mà không phải chọn lại kỳ/cơ sở/môn/lớp.

## Wording

Duy trì nguyên tắc nhận định mềm:

- Có dấu hiệu học thật
- Có khả năng treo máy
- Dấu hiệu bất thường cần kiểm tra
- Chưa đủ dữ liệu
- Chưa thấy bất thường rõ

Không dùng kết luận khẳng định như gian lận/vi phạm chắc chắn.
