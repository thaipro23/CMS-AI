# Batch 35.2 — Subject Management theo học kỳ

## Phạm vi giao diện

Route `/subject-management`:

- Có filter Hệ, Học kỳ, Nền tảng và Tìm kiếm.
- Không còn filter Block.
- Một dòng tương ứng một môn trong học kỳ.
- Cột `Phạm vi Block` hiển thị các Block đang có.
- Cột `Nền tảng học kỳ` cập nhật toàn bộ delivery theo Block.
- Cột `Vận hành theo Block` mở đúng dashboard, kế hoạch hoặc import của delivery cụ thể.

## Trạng thái chưa đồng nhất

Dữ liệu cũ có thể có CMS ở Block 1 nhưng Udemy ở Block 2. Màn hình hiển thị:

```text
Khác nhau giữa các Block
```

Người dùng chọn CMS, Udemy hoặc Chưa chọn để chuẩn hóa toàn bộ Block trong học kỳ.

## UAT bắt buộc

1. Chọn một học kỳ có hai Block và xác nhận mỗi môn chỉ xuất hiện một dòng.
2. Chọn Udemy cho một môn, kiểm tra cả hai delivery trong DB đều là `udemy`.
3. Bỏ chọn, kiểm tra cả hai delivery trở về `NULL`.
4. Mở `Vận hành theo Block`, xác nhận link dùng đúng delivery ID.
5. Tạo danh mục kỳ mới, xác nhận lựa chọn nhất quán từ kỳ trước được kế thừa.
6. Xác nhận kế hoạch và tiến độ không được sao chép sang kỳ mới.
7. Với môn kỳ trước bị mixed CMS/Udemy, xác nhận kỳ mới là `Chưa chọn`.
8. Kiểm tra responsive 1440, 1366, 1024, 768 và 390 px.
