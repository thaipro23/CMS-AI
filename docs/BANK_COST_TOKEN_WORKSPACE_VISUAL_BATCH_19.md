# Bank Cost & Token Workspace — Batch 19

## Phạm vi

Chuẩn hóa trang `/bank` thành workspace Chi phí & Token theo ảnh chốt, giữ nguyên AppShell, API, RBAC và dữ liệu usage thực tế.

## Thay đổi giao diện

- Thu gọn khoảng cách, chiều cao card, typography và section để khớp mật độ giao diện tham chiếu.
- Giữ Page identity gồm icon, tiêu đề, mô tả và scope hiện tại.
- Thanh lọc thời gian gồm preset, từ ngày, đến ngày, áp dụng, nguồn dữ liệu, thời điểm cập nhật và tải lại.
- Thông báo usage có nút đóng riêng, không đè icon hoặc nội dung.
- Bốn KPI hiển thị cùng một hàng desktop với nền phân biệt theo ngữ nghĩa.
- Khối Chi phí theo ngày dùng biểu đồ đường, đơn vị VND, legend và tổng/trung bình/cao nhất.
- Khối Cơ cấu token chuyển sang donut chart, legend và tổng token giống bố cục tham chiếu.
- Giữ nguyên hai phần nghiệp vụ phía dưới:
  - Môn học sử dụng chi phí nhiều nhất.
  - Chi tiết chi phí theo bộ đề.
- Responsive: desktop 4 KPI, tablet 2 KPI, mobile 1 KPI; chart và filter wrap an toàn.

## Sửa filter ngày end-to-end

- Tách giá trị ngày đang nhập khỏi filter đã áp dụng; thay đổi input không tự gọi API trước khi bấm `Áp dụng`.
- Preset Hôm nay / 7 ngày / 30 ngày áp dụng ngay và đồng bộ URL.
- Custom range kiểm tra thiếu ngày và `Từ ngày > Đến ngày` trước khi gửi request.
- Backend trả 422 với thông báo rõ ràng cho custom range không hợp lệ.
- Boundary ngày được hiểu theo `Asia/Ho_Chi_Minh`, sau đó chuyển sang UTC để query `UsageLog.created_at` đang lưu naive UTC.

## File thay đổi

- `frontend/app/bank/_components/pages/BankDashboardPage.tsx`
- `frontend/styles/bank-cost-dashboard.css`
- `backend/app/services/bank_cost_analytics.py`
- `backend/app/api/routes/question_bank_v2.py`

Không chạy lint, TypeScript check, build hoặc browser test theo yêu cầu của người dùng.
