# Release v25.9.16.7.2.64.16.4

## Operations + Catalog + Settings + RBAC UX

Bản này tiếp tục trực tiếp từ `.64.16.3`. Không viết lại backend và không thay workflow nghiệp vụ.

## Shared workspace

Thêm `frontend/components/operations/OperationsWorkspace.tsx`:

- `OperationsKpiStrip`
- `CompactFilterBar`
- `WorkspaceTabs`
- `WorkspaceSection`
- `SideDrawer`
- `InfoPairGrid`

Drawer có Escape, focus trap và trả focus về control trước đó. Tab hỗ trợ phím mũi tên, Home và End.

## Tác vụ nền

- KPI và filter compact.
- Cột mặc định chỉ giữ việc, trạng thái, tiến độ và thời điểm.
- Scope, người tạo và message dài chuyển thành cột tùy chọn hoặc drawer.
- Retry chỉ hiển thị trong chi tiết khi backend cho phép.
- Quiz gần đây dùng drawer và EnterpriseDataTable riêng.

## Nhật ký hoạt động

- Filter compact, giữ URL state và server-side pagination.
- Bảng ưu tiên thời điểm, người thực hiện, hành động và kết quả.
- Target, message, error và action code đầy đủ mở trong drawer.
- Export CSV và backend RBAC giữ nguyên.

## Đồng bộ AP

- Bố cục theo `Kế hoạch đồng bộ → Tiến trình & kết quả`.
- Không còn CTA kéo ngang toàn màn hình hoặc bảng kết quả raw.
- Không hard-code học kỳ; frontend lấy học kỳ từ AP sync options.
- Giữ dry-run, confirm phạm vi, job Celery, polling và chống job trùng.

## Cơ sở và Học kỳ

- Dùng EnterpriseDataTable compact.
- Status dùng icon + text + semantic tone.
- Action destructive đưa vào menu/confirm thay vì nút đỏ lớn.
- Học kỳ gộp Block 1/2 thành cột lịch, giảm chiều rộng.
- Editor block/6 tuần chuyển sang card responsive, ngày hiển thị theo quy ước Việt Nam.

## Cài đặt

Chia thành tab:

1. Giới hạn tạo câu hỏi
2. Mô hình & worker
3. Kết nối Open edX
4. SSO & xác thực
5. Chi phí & pricing

Secret không được ghi vào runtime JSON; UI chỉ hiển thị trạng thái masked từ env/secret manager.

## Người dùng & phân quyền

- User-first: một người dùng là một dòng.
- Hiển thị role hiệu lực, scope và số assignment.
- Drawer chi tiết cho quyền trực tiếp, trạng thái, lý do, người cấp và thu hồi.
- Panel gán quyền theo role → scope type → scope cụ thể → preview hiệu lực.
- SYSTEM_ADMIN, DEPARTMENT_HEAD, SUBJECT_OWNER, QUESTION_REVIEWER, CAMPUS_OWNER và TEACHER_ASSIGNED giữ đúng backend resolver hiện tại.
- Import Excel chuyển thành công cụ phụ trong drawer.

## Boundary

- Không Bootstrap/React-Bootstrap.
- Không migration mới.
- Không thay backend RBAC, API, Celery, Bank hierarchy hoặc Open edX semantics.
- Assignment score write vẫn externalized (`HTTP 410`).
