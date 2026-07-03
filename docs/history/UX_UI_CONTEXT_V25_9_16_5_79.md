# UX/UI context v25.9.16.5.79

Dùng bản này làm context tiếp theo nếu cần sửa UI:

- Hướng UI hiện tại: enterprise admin console, nền sáng, data-dense, ít màu, active state rõ, card phẳng, bảng dễ scan.
- Không quay lại dark cockpit quá nhiều màu.
- Các token chính nằm cuối `frontend/app/globals.css`, prefix `--od-*`.
- Shell chính nằm trong `frontend/components/layout/AppShell.tsx`.
- Page ưu tiên polish sâu: `/teacher-management`.
- Các màn còn lại được polish bằng global selectors để đồng bộ trước, sau đó mới tách từng page nếu cần.
- Loading ưu tiên skeleton, không spinner/text đơn thuần.
- Empty state phải nói rõ vì sao trống và người dùng nên làm gì tiếp.
- Table phải có sticky header, hover row, zebra scanning, thanh cuộn ngang trong table container.
- Filter bar nên sticky ở desktop, chuyển static ở tablet/mobile.
- Không hiện nút disabled vì thiếu quyền; permission hidden vẫn theo logic v77.
- Không sửa nghiệp vụ trong bản này.
