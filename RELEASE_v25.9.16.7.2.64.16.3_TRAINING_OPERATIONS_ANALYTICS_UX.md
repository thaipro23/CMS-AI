# Release v25.9.16.7.2.64.16.3

## Training Operations + Analytics UX

Bản `.64.16.3` tiếp tục trực tiếp từ `.64.16.2`, tập trung vào các workflow đào tạo có lượng dữ liệu lớn: quản lý sinh viên, quản lý giảng viên và phân tích học tập. Bản này không thay đổi API/database hoặc nghiệp vụ Bank.

## Thay đổi chính

### 1. Shared Training workspace

Thêm foundation dùng chung:

- `TrainingWorkflowSteps`
- `TrainingContextChips`
- `TrainingKpiStrip`
- `TrainingMappingEmptyState`

Các component này chuẩn hóa step navigation, context hiện tại, KPI compact và trạng thái thiếu mapping/dữ liệu mà không tạo card lồng card.

### 2. Student Management

#### Danh sách môn

- Dùng KPI strip chung và table contract compact.
- Ưu tiên Môn, Quy mô, Đồng bộ CMS, Course CMS, Học tập CMS và Thao tác.
- Cột phụ được ẩn theo priority trước khi phát sinh cuộn ngang.
- Giữ server-side pagination/filter và URL state.

#### Danh sách lớp theo môn

- Chuyển hoàn toàn sang `EnterpriseDataTable`.
- Bổ sung `block_id` vào URL state.
- Filter block, trạng thái và tìm kiếm dùng debounce/URL-preserved state.
- Cột học tập chi tiết là optional, không chiếm chiều rộng mặc định.

#### Chi tiết lớp

- Chuẩn hóa PageHeader, action bar, KPI strip và thông tin ngữ cảnh.
- Khi chưa ghép Course CMS, hiển thị empty state rõ ràng thay vì giao diện bán lỗi.
- Loại bỏ modal/control ghi điểm Assignment đã chết; Assignment tiếp tục chỉ đọc snapshot từ hệ thống ngoài.

### 3. Teacher Management

- Trang chính dùng KPI strip compact, giảm số summary card lặp.
- Danh sách lớp của giảng viên chuyển từ bảng ma trận rộng sang `EnterpriseDataTable`.
- Không hydrate lại toàn bộ dữ liệu ở list page; giữ list-first và lazy drill-down.
- Cột mặc định tập trung vào Lớp, Môn, Sinh viên, Course CMS, Tiến độ, Cảnh báo và Thao tác.
- Assessment/eligibility chi tiết là cột tùy chọn.

### 4. Analytics three-step workflow

`/analytics/learning` được chuẩn hóa thành:

```text
1. Chọn môn
2. Chọn lớp
3. Xem kết quả
```

- Mỗi bước chỉ hiển thị dữ liệu cần thiết cho quyết định hiện tại.
- Danh sách môn, lớp và kết quả đều dùng `EnterpriseDataTable`.
- KPI dùng component compact chung.
- Context Học kỳ/Cơ sở/Môn/Lớp hiển thị nhất quán.
- Chưa ghép Course CMS có empty state nghiệp vụ; lỗi mạng/API được diễn đạt bằng tiếng Việt, không lộ raw `Failed to fetch`.
- Backend vẫn lọc theo phạm vi SYSTEM_ADMIN, CAMPUS_OWNER và AP-assigned teacher.

### 5. URL state

`useAcademicTableState` bổ sung `blockId`/`block_id`, giúp filter lớp giữ đúng sau F5, Back và chia sẻ URL.

## Boundary được bảo toàn

- Không thêm Bootstrap/React-Bootstrap/Metronic/jQuery.
- Không thay API contract.
- Không thay backend RBAC hoặc scope inheritance.
- Không thay AP/CMS sync, analytics pipeline hoặc Celery semantics.
- Không thay Bank hierarchy, Release, Quiz, publish hoặc rollback.
- Không khôi phục Assignment score write.
- Không có migration mới; migration cuối là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.

## Verification

- Backend compileall: PASS.
- Frontend TypeScript: PASS.
- `.64.16.3` release contract: 9 passed.
- Selected current-contract regression: 63 passed; 14 historical assertions deselected because they require obsolete versions, removed theme persistence, old 52px selection geometry, or production-visible diagnostics UI.
- Next.js production build: compiled, 29/29 pages generated, build traces completed, `.next/standalone/server.js` created.
- UX source gate: READY 24/24.
- Security static simulation: READY 20/20.
- Maintainability: 0 blocker, 6 inherited large-file warnings.

Browser UAT with production-like data and real roles remains required before production sign-off.
