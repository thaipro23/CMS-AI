# v25.9.16.5.80 — Header Overlap Fix & Density Cleanup

## Mục tiêu

Sửa phản hồi UX/UI sau v79:

- Header đang che nội dung khi cuộn.
- Một số khối hero/note quá lớn nhưng không hỗ trợ thao tác trực tiếp.
- Teacher Management cần gọn hơn để ưu tiên bảng, filter và số liệu thật.

## Đã sửa

- Đổi `product-command-topbar` từ sticky sang static để không che filter/table header.
- Rút gọn topbar: bỏ section label/mô tả dài, chỉ giữ title + trạng thái phiên.
- Rút gọn sidebar: bỏ nhãn phụ/description, giảm chiều cao item, ẩn badge “Enterprise console”.
- Rút gọn session card ở sidebar.
- Xóa hero lớn, operator note và quality grid khỏi `/teacher-management`.
- Thay bằng thanh compact gồm scope hiện tại + nút Tải lại/Xuất Excel.
- Nén filter, KPI, notice, table cell để tăng mật độ dữ liệu.
- Giữ logic báo cáo/page/drill-down, không đổi API/backend.

## Kiểm tra

```bash
npm --prefix frontend run typecheck
python3 -m compileall -q backend/app
```
