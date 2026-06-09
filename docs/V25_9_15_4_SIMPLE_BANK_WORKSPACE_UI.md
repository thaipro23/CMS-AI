# v25.9.15.4 - Simple Bank Workspace UI

## Mục tiêu

Giao diện Ngân hàng đề không được bắt giáo viên đi qua nhiều bước kỹ thuật. Trang `/bank` giờ đi đúng cây vận hành:

```
Bộ môn -> Môn -> Phiên bản môn -> Bài/Chapter -> Workspace
```

Trong workspace của một bài, người dùng thấy thống kê, tài liệu, tạo câu hỏi, release/library và danh sách câu hỏi. Phần map khóa học Open edX và tạo quiz được tách sang `/bank/quiz` vì cần release đã publish và mapping an toàn trước.

## Thay đổi chính

- Sửa `/bank` thành một trang workspace đơn giản.
- Tách mapping Open edX và Quiz sang `/bank/quiz`.
- Ẩn các khái niệm kỹ thuật khỏi luồng chính: release/library vẫn có nhưng chỉ hiện khi cần publish.
- Bank Version dropdown chỉ lọc theo Chapter đang chọn để tránh hiển thị trùng lặp gây rối.
- Khi clone phiên bản môn, Bank Version clone được đặt title theo target offering, ví dụ `WEB107_FA25 - Bài 1 - v2.0`, không giữ nguyên title của version nguồn.
- Trang `/bank/quiz` chỉ cho mapping khi Release đã `published`; không tạo quiz giả nếu backend chưa nối endpoint Bank Release -> native ItemBank.

## Kiểm thử đã chạy

- `python3 -m compileall -q backend/app backend/alembic`: PASS
- `npm ci --include=dev --no-audit --no-fund`: PASS
- `tsc --noEmit`: PASS
- `next build`: compiled successfully, nhưng môi trường artifact timeout ở bước static page generation/collect build traces. Cần chạy lại trong Docker build production.
