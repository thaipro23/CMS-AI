# v25.9.15.6.20 - Bank Entity Action Menu Click Hotfix

## Lỗi
Nút `...` cạnh Bộ môn / Môn / Phiên bản môn / Bài hiển thị nhưng không mở menu.

## Nguyên nhân
Component cũ dùng `details/summary` nhưng handler lại gọi `event.preventDefault()` trên click của wrapper. Vì vậy browser không toggle được `details open`.

## Cách sửa
- Đổi sang menu controlled bằng React state.
- Dùng icon `⋮` thay vì text `...`.
- Stop propagation để click nút không kích hoạt link card.
- Tăng z-index menu.

## File sửa
- `frontend/app/bank/_components/BankPages.tsx`
- `frontend/app/globals.css`
