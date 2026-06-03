# v25.9.13.17 - Global Density Fix

Mục tiêu: UI không còn phình to; cảm giác hiển thị gần với khi người dùng zoom browser 75-85%, nhưng không ép browser zoom.

Thay đổi chính:
- Giảm sidebar từ 280px xuống 220px.
- Giảm padding/card/button/input/nav toàn hệ thống.
- Giảm kích thước metric cards, table, dropdown chọn khóa học, tree node và node detail.
- Giữ topbar/header lớn ở trạng thái ẩn như các bản trước.
- `/sync` dùng layout compact hơn, phù hợp màn hình 100% zoom.

File sửa chính:
- frontend/app/globals.css
- frontend/package.json
- backend/app/core/config.py
- .env.example

Không cần build lại Open edX/CMS.
