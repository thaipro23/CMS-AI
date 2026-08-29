# UX/UI Context v25.9.16.7.2.50

Bản `.44` thêm panel compact trong chi tiết lớp:

```text
Kiểm tra identity CMS/RollNumber
```

Mục tiêu UX: admin biết ngay lớp có an toàn chạy Đồng bộ full CMS/Ghi danh CMS theo RollNumber hay không.

Panel phải gọn, không chiếm quá nhiều chiều cao, có KPI nhỏ, action rõ, sample row tối đa 5 dòng. Không dùng wording gây hiểu nhầm; đây là audit identity kỹ thuật, không phải lỗi sinh viên.

Các trạng thái chính:

```text
Sẵn sàng RollNumber
Legacy AP username
Chưa có mapping
Sẵn sàng tạo bằng RollNumber
Thiếu RollNumber
Trùng RollNumber
Trùng mapping CMS
Sai username CMS
User CMS inactive
```

Blocker cần nổi bật để admin xử lý trước khi chạy sync diện rộng.
