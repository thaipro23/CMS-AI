# Release v25.9.16.7.2.64.16.2

## Bank Review & Quiz Creation Workbench

Bản `.64.16.2` tiếp tục trực tiếp từ `.64.16.1`, tập trung vào các workflow Bank có tần suất thao tác cao. Bản này không thêm chức năng nghiệp vụ lớn và không thay đổi API/database.

## Thay đổi chính

### 1. Bank hierarchy compact

Các trang Bộ môn, Môn học, Phiên bản môn và Bài/Chapter:

- Dùng `PageHeader` và một filter bar duy nhất.
- Bỏ quick-search/description/legend lặp lại.
- Khai báo `kind`, `priority` và width theo dữ liệu thật.
- Cột số/cột phụ có độ rộng nhỏ hoặc ẩn mặc định.
- Giữ server-side filter, sort, pagination, URL state và RBAC hiện tại.

### 2. Question Review preview-first

- Danh sách câu hỏi ưu tiên nội dung câu, trạng thái, độ khó và quality.
- Concept/source là cột tùy chọn, mặc định ẩn.
- Mỗi hàng dùng action chính `Mở duyệt`; không còn nút duyệt lặp trực tiếp trên mọi hàng.
- Duyệt, từ chối và sửa thực hiện trong preview drawer có A/B/C/D, đáp án đúng, giải thích, concept/family và source evidence.
- Giữ keyboard workflow và batch selection của `.64.16.1`.

### 3. Quiz creation workbench ba bước

`/bank/quiz` được chuyển từ panel phải hẹp sang workflow toàn chiều rộng:

```text
1. Map khóa học
2. Chọn phạm vi
3. Tạo trên CMS
```

- Course ID, Subject Version và action kiểm tra/map nằm trong một vùng cấu hình compact.
- Bảng mapping ưu tiên Bài, Section/Release, quyết định tạo và readiness.
- Match detail là cột tùy chọn.
- Summary strip cho Quiz/Final test/Không tạo/thiếu Section/thiếu Release.
- Action tạo được đặt trong thanh ngữ cảnh rõ ràng, vẫn giữ confirmation modal và connector semantics.

### 4. Lịch sử Quiz/Release

- Bỏ modal chứa bảng lớn.
- Chuyển thành workspace tab `Quiz` / `Release` trực tiếp.
- Tab/filter/page/density dùng URL state.
- Giữ rollback, audit và frozen membership hiện có.

### 5. Bank Dashboard

- Bỏ hero marketing/decorative glow.
- Giảm chiều cao KPI, loại vòng tròn trang trí.
- Ưu tiên phạm vi, số liệu cần xử lý, tìm nhanh và công việc thực tế.

## Boundary được bảo toàn

- Không thêm Bootstrap/React-Bootstrap/Metronic/jQuery.
- Không thay API contract.
- Không thay backend RBAC hoặc scope inheritance.
- Không thay publish, rollback, Open edX timer/problem-bank semantics.
- Không khôi phục Assignment score write.
- Không có migration mới; migration cuối là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.

## Verification

- Backend compileall: PASS.
- Frontend TypeScript: PASS.
- `.64.16.2` release contract: 8 passed.
- Selected Bank/Quiz/RBAC regression: 48 passed, 8 historical assertions deselected because they assert obsolete version/geometry/Assignment-write contracts.
- Next.js production build: compiled, 29/29 pages generated, build traces completed, `.next/standalone/server.js` created.
- UX source gate: READY 24/24.
- Security static simulation: READY 20/20.
- Maintainability: 0 blocker, 6 inherited large-file warnings.
- Shell syntax and Docker Compose YAML: PASS.

Browser UAT with production-like data and real roles remains required before production sign-off.
