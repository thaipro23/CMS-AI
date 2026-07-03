# UX/UI Context v25.9.16.7.2.12

## Chủ đề

Bản này không đổi layout lớn. Mục tiêu là làm dữ liệu đồng bộ đủ và đúng để UI không bị thiếu lớp.

## Nguyên tắc hiển thị lớp sau fix

Một lớp AP được xem là khác lớp khác nếu khác một trong các scope sau:

- Hệ: Poly / PTCĐ
- Cơ sở
- Kỳ
- Block
- Môn
- Mã/tên lớp

UI không được gộp lớp chỉ vì tên lớp giống nhau. Khi hiển thị bảng lớp, nên luôn cho người dùng thấy ít nhất:

- STT
- Lớp
- Môn
- Kỳ / Block
- Cơ sở
- Số sinh viên
- Trạng thái CMS

## Lưu ý vận hành

Nếu sau sync thấy thiếu lớp, kiểm tra theo full scope trước khi kết luận AP không trả dữ liệu. Cùng class_code nhưng khác campus là hợp lệ và phải được giữ thành các row khác nhau.
