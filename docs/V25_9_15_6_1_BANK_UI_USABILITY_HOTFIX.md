# v25.9.15.6.1 - Bank UI Usability Hotfix

Mục tiêu: sửa UI ngân hàng đề theo đúng hướng người dùng dễ dùng, không nhồi quá nhiều thao tác vào một màn hình.

## Đã sửa

- Các trang danh sách chỉ còn danh sách + tìm kiếm + nút thêm.
- Form thêm Bộ môn/Môn/Version môn/Bài chuyển vào popup.
- Thêm bài chỉ nhập tên bài; số bài và ID do hệ thống tự tạo.
- Vào workspace của Bài sẽ tự khởi tạo Bank Version nếu chưa có, không còn nút “Bắt đầu”.
- Upload tài liệu cho Bank Version bỏ `Content-Type: application/json` khi gửi `FormData`, tránh lỗi upload file.
- Danh sách tài liệu có nút Xem và Xóa.
- Backend có endpoint xóa tài liệu: `DELETE /api/question-bank-v2/material-versions/{material_version_id}`.
- Khi upload/xóa tài liệu trong version clone, hệ thống tự đánh dấu tài liệu thay đổi và chạy kiểm tra khác biệt.
- Kết quả khác biệt hiện trong popup: tỷ lệ giống tài liệu, số câu giữ được, số câu nên bỏ, số câu cần xem lại.
- Tạo câu hỏi có chỉ tiêu của bài và chặn tạo vượt chỉ tiêu.
- Chốt Release không bắt nhập mã release; backend tự sinh mã release.
- Danh sách câu hỏi chuyển từ bảng sang thẻ câu hỏi dễ đọc hơn.
- Tạo Quiz không còn nằm trong workspace bài.

## API mới

```http
DELETE /api/question-bank-v2/material-versions/{material_version_id}
```

Payload generate bổ sung:

```json
{
  "question_count": 10,
  "target_question_count": 120,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20
}
```

Nếu số câu đang có + số câu muốn tạo vượt `target_question_count`, backend trả lỗi rõ ràng.

## File chính đã sửa

```text
backend/app/api/routes/question_bank_v2.py
backend/app/schemas/question_bank.py
backend/app/services/question_bank_service.py
frontend/app/bank/_components/BankPages.tsx
frontend/lib/api.ts
frontend/types/index.ts
frontend/app/globals.css
```
