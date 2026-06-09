# v25.9.15.6.4 - Bank Popup Document Preview Hotfix

## Mục tiêu

Sửa popup xem tài liệu trong Chapter Workspace. Bản trước hiển thị mỗi chunk thành một khung cuộn riêng nên giao diện rối, khó đọc và bị nhiều thanh scroll chồng nhau.

## Thay đổi

- Popup dùng một vùng nội dung duy nhất.
- Popup xem tài liệu được mở rộng chiều ngang.
- Nội dung tài liệu được gộp vào một khung đọc duy nhất.
- Header popup cố định, có nút Đóng rõ ràng.
- Khi mở popup, trang nền không bị cuộn theo.
- Bấm ESC để đóng popup.

## File sửa

- `frontend/app/bank/_components/BankPages.tsx`
- `frontend/app/globals.css`

## Không thay đổi

- Không thêm migration.
- Không đổi API backend.
- Không đổi logic upload/xóa tài liệu.
