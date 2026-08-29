# Release v25.9.16.7.2.64.16

## App Shell & Enterprise UI Rebuild + Production UI Hardening

### Giao diện nền

- Sidebar desktop collapsed 64px, expanded 220px.
- Preference sidebar lưu bằng localStorage và được bootstrap trước hydration.
- Mobile dùng off-canvas drawer, overlay, Escape, focus trap, inert và trả focus về nút mở.
- Top bar 56px chỉ chứa sidebar toggle, breadcrumbs, trạng thái CMS, theme và user menu.
- Light/dark mode dùng semantic tokens và lưu preference.
- Không dùng Metronic, jQuery, Bootstrap, Unicode icon hoặc icon font.

### Navigation và RBAC

- Menu được chia theo Tổng quan, Ngân hàng đề, Vận hành đào tạo, Vận hành hệ thống, Danh mục và Quản trị.
- Menu không có quyền bị ẩn hoàn toàn.
- Route guard frontend dùng permission hiện có; backend vẫn là lớp authorization cuối cùng.
- Giữ nguyên hierarchy Bank và scope inheritance `.64.15`.

### Table và layout

- Content full-width, không có max-width cố định cho màn quản trị dữ liệu.
- Body không scroll ngang.
- Table container có horizontal scroll riêng.
- STT 64px, selection 52px, sticky offset theo geometry contract.
- Raw legacy tables nhận cùng typography, header, spacing, border và hover contract trong khi chờ migrate hoàn toàn sang `EnterpriseDataTable`.
- `PageHeader` dùng chung được áp dụng cho các màn vận hành chính.

### Production UI hardening

Mặc định production:

```env
NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
```

Ẩn hoặc vô hiệu hóa frontend:

- Ops Readiness/UAT gates.
- UX acceptance và attack simulation UI.
- Analytics class doctor và các nút recalculate thủ công trên giao diện production.
- Nút test GPT/Open edX.
- Mock LLM/Open edX control.
- Demo auth option.
- Default demo username/course state.

Backend diagnostics endpoints không bị xóa để monitoring nội bộ vẫn sử dụng được theo RBAC.

### Database

Không có migration mới; latest vẫn là `0052`.

### Verification cuối

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Release contract: 10 passed
Selected regression: 42 passed
Production build: 29/29 static pages, standalone created
UX source gate: READY 24/24
Security attack simulation: READY 20/20
Maintainability: 0 blocker, 6 cảnh báo kế thừa
```
