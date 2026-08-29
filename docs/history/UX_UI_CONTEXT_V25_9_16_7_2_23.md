# UX/UI Context v25.9.16.7.2.23 — Sticky Student Identity Columns

## Vấn đề

Trong bảng sinh viên có nhiều cột điểm/thành phần, khi cuộn ngang, `STT` còn đứng lại nhưng `Sinh viên` có thể bị cuộn đi hoặc bị lệch do các rule `.sticky-col { left: 0 }` cũ. Điều này làm người dùng không biết dòng điểm đang thuộc sinh viên nào.

## Quyết định UI

- `STT` là cột cố định thứ nhất, `left: 0`.
- `Sinh viên` là cột cố định thứ hai, `left: var(--sticky-stt-width)`.
- Hai cột dùng class rõ ràng: `sticky-index-col` và `student-sticky-col`.
- Không dựa vào selector rộng hoặc `:has()` để xác định cột định danh.
- Áp dụng cho chi tiết lớp và bảng kết quả hành vi học.

## Kết quả mong muốn

Khi cuộn ngang, người dùng luôn nhìn thấy đồng thời số thứ tự và định danh sinh viên.
