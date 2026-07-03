# UX/UI Context v25.9.16.7.2.21

## Auto map tất cả

- Đây là hành động nặng, có thể ảnh hưởng hàng nghìn lớp.
- UI không được giữ spinner dài trong request.
- Bấm nút chỉ tạo job nền.
- Sau khi tạo job, người dùng có thể F5/chuyển trang; tiến trình vẫn còn.
- Người dùng khác mở `/jobs` cũng nhìn thấy job đang chạy.

## `/student-management`

- Nút vẫn là `Auto map tất cả`.
- Khi bấm xong hiển thị thông báo job nền + link `Xem Jobs`.
- Nếu có job đang chạy cho bộ lọc hiện tại, hiển thị `Auto map đang chạy nền`.

## `/jobs`

- Có nhóm việc mới: `Auto map / đồng bộ hàng loạt`.
- Job hiển thị tên: `Auto map tất cả + đồng bộ CMS`.
- Child job lớp vẫn hiện dưới nhóm `Đồng bộ lớp/CMS` với loại `Đồng bộ full CMS`.
