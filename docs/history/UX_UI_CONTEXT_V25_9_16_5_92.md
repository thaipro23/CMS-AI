# UX/UI Context v25.9.16.5.92

## Chi tiết lớp

Cột **Tiến độ học** trong bảng sinh viên phải gọn, chỉ có 3 dòng:

```text
Hoàn thành khóa học: 62.5%
Điểm tổng: 8/10
Điểm thấp
```

Không thêm dấu chấm sau trạng thái.

## Cuộn ngang

- Chỉ vùng **Danh sách sinh viên** được cuộn ngang khi bảng có nhiều cột Quiz.
- Các thẻ KPI, action bar, bộ lọc, và thông tin phía trên không được trôi ngang theo bảng.
- Không hiển thị hướng dẫn kiểu “Kéo ngang trực tiếp trong bảng, dùng touchpad, hoặc giữ Shift...” trên UI.
- Không dùng custom drag/Shift-wheel handler; ưu tiên native scrollbar ổn định, dễ hiểu.

## Không thay đổi

- Không đổi logic sync điểm/course completion của v90/v91.
- Không thêm diagnostics ồn vào màn chi tiết lớp.
