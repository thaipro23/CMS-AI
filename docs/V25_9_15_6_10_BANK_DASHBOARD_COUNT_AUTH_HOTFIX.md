# v25.9.15.6.10 - Bank Dashboard Count + Refresh Auth Hotfix

## Mục tiêu

Sửa các lỗi UI/logic được phát hiện sau bản v25.9.15.6.9:

- Dashboard hiển thị số còn việc phải dựa trên `tổng - đã xong`/số thực sự còn câu chưa xử lý, không tính nhầm các bộ môn/môn/version trống là còn việc.
- F5 ở các trang Bank không được gọi API bằng header demo khi token phiên làm việc chưa nạp xong, tránh `401 Unauthorized`.
- `/bank` không gọi `dashboard/overview` lặp 2 lần do trạng thái auth ban đầu đổi sau khi refresh.

## Thay đổi backend

File:

```text
backend/app/services/question_bank_service.py
```

Dashboard overview giờ tính:

```text
còn việc = có pending_review / needs_review / draft_error
đã xong = tổng - còn việc
```

Không tính bộ môn/môn/version trống là “còn việc” nếu không có câu chờ duyệt hoặc câu lỗi.

## Thay đổi frontend

File:

```text
frontend/context/AppContext.tsx
frontend/app/bank/_components/BankPages.tsx
```

### Auth khi F5

`authHeaders()` đọc token từ `sessionStorage` ngay cả khi state React chưa kịp hydrate, nên request đầu tiên sau F5 vẫn có Bearer token.

### Dashboard overview

Trang `/bank` chỉ load overview sau khi auth đã sẵn sàng, đồng thời có guard tránh gọi trùng cùng một bộ header.

### Card số liệu

Dashboard đổi sang hiển thị dễ hiểu:

```text
Bộ môn: tổng
x đã xong · y còn việc

Môn: tổng
x đã xong · y còn việc

Version môn: tổng
x đã xong · y còn việc
```

## Không thêm migration

Bản này không thay đổi schema database.
