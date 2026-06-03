# v25.9.12.13 — Full Node Content + Refetch Optimization

## Mục tiêu
Sửa đúng vấn đề “Node Detail phải hiển thị full nội dung” và không để Generation Planner tự cắt 40 chunks đầu.

## Đã sửa
- `/sync` không refetch toàn bộ cây nội dung mỗi lần chọn node.
- Tách tải cấu trúc course tree/nodes khỏi tải summary/preview của node đang chọn.
- Node detail dùng phân trang `/chunks/page` để lấy toàn bộ chunks của node, không còn giới hạn 200 chunks ở frontend.
- Generation Planner bỏ hard limit 40 chunks. Khi giáo viên chọn node/course, planner dùng toàn bộ chunks trong scope; Cost Control/quota chịu trách nhiệm chặn nếu quá lớn.
- Thêm regression test đảm bảo query 55 chunks không bị cắt còn 40.

## Lưu ý
Nếu một node/course quá lớn, estimate/cost limit có thể chặn generate. Đây là đúng hành vi: UI được xem full nội dung, còn generate phải qua Cost Control.
