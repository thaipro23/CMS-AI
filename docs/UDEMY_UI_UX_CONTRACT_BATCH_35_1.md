# Batch 35.1 — Udemy UI/UX Contract and Browser Acceptance

## Design contract được áp dụng

- AppShell, topbar, breadcrumb và main workspace dùng component chung.
- Page identity → notice/job state → KPI → tabs → filter → section → EnterpriseDataTable.
- Chỉ table viewport cuộn ngang; trang không tạo horizontal overflow.
- Button, notice, badge, progress và empty/error state dùng component/token chung.
- Tablet/mobile giữ action truy cập được, filter xếp dọc và modal không che footer.

## Luồng cần UAT

### Dashboard

1. Mở `/subject-management/{deliveryId}/udemy` bằng system admin.
2. Xác nhận `Tổng quan` khác nội dung với bảng `Tiến độ sinh viên`.
3. Chọn `Đạt tiến độ`, chuyển sang `Cảnh báo`; option này phải biến mất và chỉ còn row cảnh báo.
4. Kiểm tra keyboard Arrow/Home/End giữa các tab.
5. Kiểm tra progressbar bằng screen reader/accessibility tree.

### Import

1. Mở modal import trên desktop và mobile.
2. Xác nhận wording `file tổng hợp tiến độ 7 cột`.
3. Queue file hợp lệ, sau đó F5 khi job đang chạy.
4. Job notice phải được khôi phục, không được tạo job mới bằng nút Import.
5. Khi hoàn tất, KPI/dashboard tự tải lại.

### Export

1. Tạo export theo từng filter/class/scope.
2. F5 khi job đang queued/running; job phải tiếp tục hiển thị.
3. Mô phỏng lỗi polling: không được bật nút để tạo job trùng; phải có `Thử đọc lại trạng thái`.
4. Mô phỏng lỗi download sau khi completed; phải có `Tải lại file` và giữ job ID.

### Responsive

Chạy tại 1440, 1366, 1024, 768 và 390 px:

- Không có horizontal overflow ở document.
- Bảng nhiều cột cuộn trong `.enterprise-table-scroll`.
- Sidebar mobile là drawer.
- Modal import toàn màn hình phù hợp và footer không che form.

## Acceptance gate

Chỉ đánh dấu production UI accepted khi có:

- Frontend production build thành công.
- Playwright desktop/mobile thành công trên UAT hoặc môi trường tương đương.
- Evidence system admin, teacher và campus owner.
- Không có browser runtime error/console error nghiêm trọng.
- Export/import hoàn tất thật với Redis/Celery và dữ liệu UAT.
