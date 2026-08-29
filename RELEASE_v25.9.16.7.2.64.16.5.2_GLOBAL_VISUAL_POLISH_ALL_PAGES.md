# v25.9.16.7.2.64.16.5.2 — Global Visual Polish All Pages

## Mục tiêu

Chuẩn hóa toàn bộ giao diện production của AI Server / Open edX CMS theo một visual language enterprise thống nhất: có icon, nền semantic nhạt, section rõ ràng, card bo tròn nhẹ và hierarchy dễ quét mắt, đồng thời giữ nguyên toàn bộ nghiệp vụ hiện có.

## Thay đổi toàn hệ thống

### Visual foundation

- Bổ sung `VisualIcon` làm lớp ánh xạ icon/tone semantic dùng chung.
- Mở rộng `AppIcon` bằng các icon Bank, Training, Analytics, Ops, Catalog, Security, Cost và action.
- Nạp `global-visual-polish.css` cuối chuỗi stylesheet để tạo một contract thị giác thống nhất.
- Giữ sidebar tối và workspace sáng; không khôi phục dark mode toàn trang.

### Page header và section

- `PageHeader` có icon semantic, title/subtitle/action rõ hierarchy.
- `WorkspaceSection`, `StatPanel`, filter card và section legacy có icon/nền nhấn/bo góc đồng nhất.
- Breadcrumb, topbar, modal và drawer được polish nhưng không thay navigation hoặc focus contract.

### KPI và summary

- `MetricCard`, Training KPI, Operations KPI, Bank dashboard KPI và các summary grid có icon chip, số liệu chính, mô tả phụ và semantic tone.
- Không hard-code KPI; số liệu tiếp tục lấy từ API và tôn trọng filter hiện tại.

### Notice, status và empty/error state

- `InlineNotice`, `ActionMessage`, `StatusBadge` và `TableStates` dùng SVG icon thay cho Unicode marker.
- Success/warning/error/info có nền nhạt, border và icon tương ứng.
- Không hiển thị raw API error nếu frontend đã có semantic error mapper.

### Enterprise tables

- Giữ contract full-content của `.64.16.5.1`.
- Tất cả cột hiển thị mặc định, tự co giãn theo loại dữ liệu và xuống dòng khi cần.
- STT, checkbox, số, status và action giữ compact; cột nội dung nhận không gian còn lại.
- Header/summary/table surface được polish nhưng URL state, server-side filter/sort/pagination, sticky columns và column visibility không thay đổi.

## Phạm vi trang

Visual contract được áp dụng cho toàn bộ production routes thuộc:

- Dashboard và Bank hierarchy.
- Search, question review, Quiz và history.
- Student Management, Teacher Management và Analytics.
- Jobs, Audit và AP Sync.
- Premises và Semesters.
- Users/RBAC và Settings.
- Auth callback và các trang redirect/compatibility.

Static report ghi nhận 33 active page files và 8 redirect page files trong frontend.

## Boundary kỹ thuật

- Không thêm Bootstrap, React-Bootstrap, jQuery hoặc Metronic.
- Không thay API contract.
- Không thay backend RBAC hoặc scope inheritance.
- Không thay Celery workflow.
- Không thay Bank publish/rollback hoặc Open edX semantics.
- Không thay database schema; không có migration mới.
- Assignment score write vẫn externalized.

## Verification tóm tắt

- Backend compileall: PASS.
- Frontend TypeScript: PASS.
- Release tests: 8 passed.
- Current UX regression: 41 passed; 9 historical assertions deselected.
- Business regression: 30 passed; 7 historical assertions deselected.
- Next.js production build: 29/29 pages, build traces và standalone PASS.
- Global visual source contract: READY 12/12.
- UX source gate: READY 24/24.
- Security static simulation: READY 20/20.
- Production browser source contract: READY_FOR_BROWSER_UAT 12/12.
- Maintainability: 0 blocker, 6 inherited warnings.

## Lưu ý nghiệm thu

Source contract và production build đã đạt. Browser UAT trên Chrome, Edge, Safari/iPhone, Android, iPad, keyboard-only, forced-colors và từng role thật vẫn là điều kiện bắt buộc trước sign-off production.
