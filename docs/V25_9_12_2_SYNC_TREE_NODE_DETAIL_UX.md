# v25.9.12.2 - Sync Tree Node Detail UX

## Mục tiêu

Bản này sửa phần Sync để người dùng hiểu rõ sự khác nhau giữa **node CMS** và **chunk AI**.

Một node trong CMS có thể được chia thành nhiều chunk để AI xử lý theo giới hạn token. Điều này không có nghĩa là CMS có nhiều node hơn. Ví dụ `Quiz 3.1 / Trắc nghiệm cuối bài` vẫn là một node/problem trong CMS; nếu nội dung dài thì AI Server có thể tạo 2 chunk nội dung.

## Thay đổi chính

### 1. Cây nội dung có nút ẩn/hiện node con

Trang `/sync` thêm mũi tên mở rộng/thu gọn từng node. Có thêm nút:

- `Hiện tất cả`
- `Thu gọn`

### 2. Node List chuyển thành khu vực xem đầy đủ nội dung node

Khu vực bên phải không còn chỉ là danh sách node. Khi chọn một node trong cây, hệ thống hiển thị:

- tên node
- loại block
- đường dẫn node trong course
- số chunk
- số token
- source type
- toàn bộ nội dung text đã sync của node đó

### 3. Giải thích rõ chunk không phải node

UI bổ sung mô tả: một node CMS có thể có nhiều chunk nếu nội dung dài. Chunk chỉ là lát cắt để AI xử lý, không phải node mới trong CMS.

### 4. Problem/quiz ít bị tách chunk không cần thiết

Backend điều chỉnh chunk policy:

- `problem`: max 2000 tokens, overlap 0
- `transcript`: max 900 tokens, overlap 120
- `file/pdf/pptx`: max 1000 tokens, overlap 120
- các loại khác: max 900 tokens, overlap 100

Với các quiz/problem thông thường khoảng 1200 tokens, hệ thống sẽ giữ thành 1 chunk thay vì tách làm 2 chunk như trước.

## File đã sửa

- `frontend/app/sync/page.tsx`
- `frontend/app/globals.css`
- `backend/app/services/course_sync.py`
- `backend/app/core/config.py`
- `.env`
- `.env.example`
- `frontend/package.json`
- `frontend/package-lock.json`
