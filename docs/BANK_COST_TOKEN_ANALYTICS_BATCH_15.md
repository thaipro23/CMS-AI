# Batch 15 — Bank Cost & Token Analytics

## Mục tiêu

Thay trang `/bank` dạng tổng quan câu hỏi ít giá trị vận hành bằng màn hình theo dõi **chi phí GPT và token thực tế của Ngân hàng đề**.

Màn hình mới không suy đoán tiền từ số lượng câu hỏi và không tạo KPI giả. Dữ liệu chỉ lấy từ `ai_usage_log` đã được ghi sau các lần gọi model cho Bank Version.

## Luồng dữ liệu đã triển khai

```text
Tạo câu hỏi từ Bank Version
→ ModelGateway trả usage thực tế
→ Question Bank lưu câu hỏi
→ CostControlService tính chi phí theo pricing hiện hành
→ ghi ai_usage_log với course_id = bank:{bank_version_id}
→ GET /api/question-bank-v2/dashboard/cost-analytics
→ frontend /bank hiển thị KPI, biểu đồ và bảng chi tiết
```

Các phản hồi model đã bị tính phí nhưng lỗi parse cũng được giữ usage để không làm thất thoát chi phí khỏi dashboard.

## Backend

### Endpoint mới

```text
GET /api/question-bank-v2/dashboard/cost-analytics
```

Hỗ trợ:

- `date_range=today|7d|30d|custom`
- `from_date`, `to_date`
- tìm kiếm theo bộ môn, môn, phiên bản môn và bài
- server-side page/page size
- sort theo chi phí, token, lượt gọi, số câu và thời điểm gần nhất
- giới hạn dữ liệu theo RBAC Bank của người đang đăng nhập

### Dữ liệu trả về

- Tổng chi phí USD và VND.
- Input token, cached input token, uncached input token và output token.
- Tổng lượt gọi model.
- Số câu AI thực tế đã lưu.
- Bình quân chi phí trên mỗi câu.
- Tỷ lệ input token dùng cache.
- Chuỗi dữ liệu theo ngày.
- Phân bổ theo model.
- Top môn theo chi phí.
- Bảng chi tiết theo Bank Version.

### Ghi nhận usage cho Bank generation

`generate_from_bank_version` hiện tổng hợp usage từ từng tài liệu/độ khó và ghi một `UsageLog` cho operation:

```text
feature = bank_generate_questions
course_id = bank:{bank_version_id}
job_id = BankOperationJob.id nếu chạy Celery
```

Không bổ sung bảng hoặc migration mới vì sử dụng model `UsageLog` hiện có.

## Frontend `/bank`

### Page identity

```text
Chi phí & Token ngân hàng đề
Theo dõi chi phí GPT thực tế, lượng token và hiệu suất tạo câu hỏi
trong phạm vi được phân quyền.
```

### Bộ lọc

- Hôm nay.
- 7 ngày.
- 30 ngày.
- Khoảng ngày tùy chỉnh.
- URL giữ date range, search, page, page size, sort và density.

### KPI

1. Chi phí thực tế.
2. Tổng token.
3. Câu hỏi AI đã tạo và bình quân tiền/câu.
4. Token dùng cache và tỷ lệ cache.

### Khối phân tích

- Biểu đồ chi phí thực tế theo ngày.
- Cơ cấu token.
- Model usage.
- Top môn tiêu tốn chi phí.
- EnterpriseDataTable chi tiết theo bộ đề.

### Điều hướng

- Menu `/bank` đổi từ `Tổng quan` thành `Chi phí AI`.
- Trang tìm kiếm Bank quay lại `Chi phí & Token` thay vì `Tổng quan`.

## Nguyên tắc dữ liệu

- Không backfill giả cho các lượt generate lịch sử chưa có `UsageLog`.
- Không nhân số câu với một mức tiền ước lượng để giả thành actual cost.
- Dashboard có thông báo rõ khi dữ liệu lịch sử chưa được ghi.
- Chỉ các lần generate mới sau khi triển khai mới chắc chắn có telemetry đầy đủ.

## Responsive

- 4 KPI → 2 cột tablet → 1 cột mobile.
- Khối biểu đồ/token chuyển một cột dưới 1180px.
- Biểu đồ được cuộn trong chính viewport trên điện thoại.
- EnterpriseDataTable giữ chiến lược cuộn ngang riêng, không làm body cuộn ngang.

## Phần chưa xác minh

- Chưa deploy lên UAT thật để kiểm tra SSO, PostgreSQL và dữ liệu usage thực tế.
- Dữ liệu generate cũ không có UsageLog sẽ không xuất hiện.
- Không chạy TypeScript check, lint, build, unit test hoặc browser smoke test theo yêu cầu hiện tại của người dùng.
