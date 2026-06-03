# v25.9.12.11 - Remove Chunk Browser from Sync Screen

## Mục tiêu
Bỏ khu vực Chunk Browser khỏi trang `/sync` để giao diện rộng rãi hơn, tập trung vào 2 vùng chính: cây nội dung khóa học và nội dung node được chọn.

## Thay đổi
- Xóa section `Chunk Browser` khỏi `frontend/app/sync/page.tsx`.
- Bỏ các control tìm kiếm chunk, lọc source type, select course node và phân trang chunk ở màn hình sync.
- Vẫn giữ thống kê tổng chunk/token bằng cách gọi `/chunks/page` với `page_size=1`, không tải danh sách chunk lớn lên UI.
- Thêm layout `sync-tree-detail-grid` để khu vực cây node và nội dung node rộng hơn.

## Kết quả
Trang sync gọn hơn, ít cuộn hơn và phần nội dung node có nhiều không gian đọc hơn.
