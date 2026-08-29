# AP Sync Workspace Alignment Hotfix — Batch 21

## Hiện tượng

Trên `/ap-sync`, khối **Tiến trình & kết quả** bị tụt thấp hơn khối **Kế hoạch đồng bộ** khi workspace đã cuộn. Phần đầu section cũng xuất hiện hai đường phân cách và khoảng trắng thừa.

## Nguyên nhân

- `.ap-sync-recent` dùng `position: sticky` với `top: calc(var(--shell-topbar-height) + 12px)`.
- `enterprise-content` đã là scroll owner và đã nằm dưới topbar. Vì vậy topbar bị cộng thêm lần thứ hai khi sticky kích hoạt, làm cột phải lệch xuống.
- `workspace-section-head` đã có `border-bottom`, trong khi `workspace-section-body` tiếp tục có `border-top`, tạo đường kẻ kép.
- Header cột phải cho phép action wrap tự do nên nút **Làm mới** dễ rơi xuống dòng và làm phần đầu card cao bất thường.

## Thay đổi

- Bỏ sticky riêng của panel tiến trình trên trang AP Sync; hai panel luôn bắt đầu cùng một hàng.
- Giữ panel tiến trình `align-self: start` để chiều cao nội dung độc lập, không kéo giãn sai.
- Bỏ border-top lặp của body trong AP Sync.
- Chuyển header panel tiến trình sang grid 2 cột để nút **Làm mới** nằm gọn phía trên bên phải.

## File sửa

- `frontend/styles/operations-catalog-rbac-ux.css`

## Kiểm thử

Không chạy lint, typecheck, build hoặc browser test. Cần xác nhận trực quan trên UAT tại `/ap-sync` ở desktop và tablet.
