# UX/UI Context v25.9.16.6.4

## Mục tiêu

Thu gọn màn chi tiết lớp để giáo viên/quản lý đọc nhanh, không bị rối bởi các cột kỹ thuật.

## Đã chỉnh ở Danh sách sinh viên

### Cột `Sinh viên`

Gộp vào một cột:

- Mã sinh viên
- Họ tên
- Username
- CMS username nếu khác username AP
- Email
- Số lần học lại

Không còn cột riêng:

- Username
- Email
- Số lần học lại

### Cột `Tiến độ học`

Giữ đúng format ngắn:

```text
Hoàn thành khóa học: ...
Điểm tổng: ...
Điểm thấp / Đang học / Hoàn thành tốt / ...
```

Gộp xử lý CMS/enroll vào đây. Nếu chưa kiểm tra/chưa cập nhật/chưa đồng bộ CMS/chưa enroll thì chỉ hiện một dòng:

```text
Hãy bấm Đồng bộ full CMS
```

Nếu mọi thứ ổn thì không hiện dòng này.

Không còn cột riêng:

- Đồng bộ CMS
- Đã enroll

### Cuộn ngang

- Chỉ bảng sinh viên cuộn ngang.
- Các card phía trên giữ nguyên.
- Vùng scroll chuyển lên `class-student-table-shell` để khi con trỏ ở giữa bảng vẫn cuộn ngang được bằng touchpad/horizontal wheel.
- Không hiển thị hướng dẫn kéo ngang dài trên UI.

## Học online minimal UI

Thêm card `Học online` ở chi tiết lớp:

- Tổng đánh giá
- Có dấu hiệu học thật
- Có khả năng treo máy
- Dấu hiệu cần kiểm tra
- Chưa đủ dữ liệu

Thêm cột `Học online` trong bảng sinh viên:

- Nhận định mềm
- Độ tin cậy
- Hành động đề xuất

Click vào nhận định mở modal chi tiết ngắn.

## Quy tắc ngôn ngữ an toàn

Không hiển thị các từ:

- gian lận
- cheating
- không học thật
- treo máy chắc chắn
- vi phạm chắc chắn

Nhãn frontend bắt buộc:

```text
LIKELY_REAL_LEARNING -> Có dấu hiệu học thật
POSSIBLE_IDLE -> Có khả năng treo máy
POSSIBLE_CHEATING -> Dấu hiệu bất thường cần kiểm tra
INSUFFICIENT_DATA -> Chưa đủ dữ liệu
NORMAL -> Chưa thấy bất thường rõ
```

## Bước tiếp theo

v25.9.16.6.5 nên làm drawer/tab `Theo Bài / Deadline` đầy đủ:

- Timeline 6 tuần
- Bài/Session
- Phần video
- Quiz cuối Bài
- Deadline evidence
