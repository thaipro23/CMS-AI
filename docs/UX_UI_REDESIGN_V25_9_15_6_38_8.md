# v25.9.15.6.38.8 — AI Server UX/UI Redesign Foundation

## 1. Vấn đề hiện tại

AI Server là web quản lý ngân hàng đề có nhiều nghiệp vụ: bộ môn, môn, version môn, chapter, duyệt câu hỏi, phân quyền, tạo quiz, vận hành job và audit. Giao diện trước đó đã có chức năng nhưng chưa đạt chuẩn sản phẩm nội bộ cho nhân viên văn phòng 25–40 tuổi vì:

1. Visual hierarchy chưa ổn định: dashboard, vận hành và phân quyền cùng dùng nhiều card/popup, khiến người dùng khó biết việc chính cần làm là gì.
2. Sidebar tối màu làm sản phẩm giống công cụ kỹ thuật hơn là phần mềm nghiệp vụ văn phòng; trong khi yêu cầu không cần dark mode.
3. Copy UI còn lộ giải thích kiến trúc/technical phrasing, làm người ít công nghệ khó hiểu.
4. Bảng dữ liệu và trạng thái chưa đồng bộ: audit/jobs cần dạng bảng rõ ràng; dashboard cần KPI và chart có trục/legend dễ đọc.
5. Component chưa có design token nhất quán cho màu, spacing, border radius, shadow, focus state.
6. Accessibility thiếu nền tảng: skip link, focus ring thống nhất, contrast, reduced motion.

## 2. Hướng thiết kế mới

Thiết kế mới dùng mô hình **Enterprise Command Center**:

- Người dùng bắt đầu từ `/bank` để thấy KPI, việc cần xử lý, chart và tìm nhanh.
- Sidebar chỉ giữ nhóm điều hướng chính: Công việc chính, Vận hành, Quản trị.
- Các phần phụ như alert/activity/import/list mở bằng popup, tránh làm loãng trang chính.
- Bảng dữ liệu dùng header rõ, hover row, status badge và nội dung lỗi nổi bật.
- Không dùng dark mode; toàn bộ layout là light UI, phù hợp môi trường văn phòng.

## 3. Color system — 60/30/10

### 60% Neutral nền và surface

- `--ds-bg: #f7f9fc`
- `--ds-surface: #ffffff`
- `--ds-surface-soft: #f8fafc`
- `--ds-border: #dbe3ef`
- `--ds-text: #0f172a`
- `--ds-muted: #64748b`

### 30% Secondary blue-soft / information surface

- `--ds-bg-2: #eef4ff`
- `--ds-surface-blue: #eff6ff`
- `--ds-primary-soft: #dbeafe`

### 10% Primary/action and semantic

- Primary: `#2563eb`
- Primary hover: `#1d4ed8`
- Success: `#0f9f6e`
- Warning: `#d97706`
- Error: `#dc2626`
- Info: `#0284c7`

## 4. Typography

Font stack:

```css
Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif
```

Scale:

- H1 dashboard/hero: 28–44px, line-height 1.06
- H1 workspace topbar: 24px, line-height 1.18
- H2 card: 18–22px
- Body: 14px, line-height 1.55
- Table/header/caption: 11–12px, uppercase only where helpful

Contrast targets: WCAG 2.1 AA minimum. Body text uses `#0f172a` or `#334155` on white/light surfaces.

## 5. Spacing & grid

Spacing uses 4px/8px base:

- 4px: tiny inline gaps
- 8px: compact gaps, icon/text gaps
- 12px: form controls/table cell compact padding
- 16px: card internal groups
- 20/24px: page/card padding
- 28px: major shell spacing

Grid:

- Desktop shell: 256px sidebar + flexible content.
- Content max width: 1440px.
- Dashboard KPI: 4 columns desktop, 2 tablet, 1 mobile.
- Chart grid: 2 columns desktop, 1 tablet/mobile.
- Forms: 2–4 columns desktop, single column mobile.

## 6. Component redesign

### Button

States:

- Default: primary blue background, white text.
- Hover: darker blue, raised shadow.
- Active: lower transform, smaller shadow.
- Secondary: white background, blue hover surface.
- Disabled: lower opacity, no transform.

### Input/select/textarea

- 40px minimum height.
- 12px radius.
- Strong border for visible affordance.
- Focus ring `0 0 0 4px rgba(37, 99, 235, 0.18)`.

### Card

- White surface, 24px radius, low shadow.
- Hover shadow only when meaningful.
- Hero cards use blue gradient surface.

### Navigation

- Light sidebar.
- Three groups: Công việc chính, Vận hành, Quản trị.
- Active item has blue icon and subtle blue surface.
- Session/token tools moved into “Phiên làm việc” modal to reduce visual noise.

### Modal

- Large radius, blur backdrop, visible close button.
- Escape closes modal.
- Content remains readable on mobile.

### Table

- Sticky header.
- Uppercase compact header text.
- Row hover.
- Error text uses semantic red.
- Responsive horizontal scroll.

## 7. Navigation & flow

Primary user journeys:

1. Dashboard → click KPI/status/chart → filtered worklist.
2. Bank → Department → Subject → Version → Chapter → Review/edit questions.
3. Users → choose person → role → scope → save; Excel import stays in popup.
4. Jobs → table of operation jobs → identify failed/running job quickly.
5. Audit → table-based investigation.

## 8. Micro-interactions

- Sidebar active/hover: 160ms transform/background transition.
- Buttons: 160ms hover/active transition.
- KPI cards: slight elevation on hover.
- Chart legend/bar click: subtle translateX.
- Reduced motion media query disables animations for users who need it.

## 9. Responsive

Breakpoints:

- `<=1200px`: sidebar becomes top stacked navigation; dashboard KPI 2 columns.
- `<=760px`: single-column layout, compact padding, hero title smaller, tables scroll horizontally.

## 10. Accessibility

Implemented foundation:

- Skip link to main content.
- `aria-current="page"` for active navigation.
- Visible focus ring on form controls and skip link.
- WCAG AA color contrast for text/status surfaces.
- Reduced motion support.
- Modal `role="dialog"` and `aria-modal="true"`.

## 11. Code changes

Key files:

- `frontend/components/layout/AppShell.tsx`
- `frontend/app/globals.css`
- `frontend/package.json`

This version is a design foundation and shell-level redesign. It keeps backend APIs unchanged and does not change database schema.
