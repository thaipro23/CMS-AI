# Release v25.9.16.7.2.64.16.1

## Enterprise Visual Foundation + Dense Table Contract + Review UX

Bản `.64.16.1` là giai đoạn đầu của kế hoạch sửa UX/UI toàn hệ thống sau khi `.64.16` không đạt visual acceptance trên dữ liệu thật. Bản này giữ nguyên backend, API, database và workflow nghiệp vụ; chỉ tái cấu trúc lớp trình bày và thao tác chính.

## Thay đổi chính

### Sidebar tối, workspace sáng

- Loại bỏ theme switcher và preference light/dark.
- Sidebar luôn tối; topbar và content luôn sáng.
- Giữ desktop collapsed `64px`, expanded `220px` và mobile drawer accessible.
- Không làm thay đổi route, breadcrumb, permission-aware navigation hoặc mobile focus behavior.

### Dense EnterpriseDataTable contract

- Thêm loại cột: `index`, `selection`, `identity`, `number`, `status`, `date`, `progress`, `actions`, `text`.
- Thêm mức ưu tiên `required`, `important`, `optional`.
- Cột STT `52px`, checkbox `44px`, cột số mặc định khoảng `72–96px`.
- Cột ít giá trị tự ẩn theo container/viewport trước khi buộc người dùng cuộn ngang.
- Hỗ trợ clamp nội dung, row active và sticky offset động.
- Tối ưu cột trên Student, Teacher, Jobs, Audit, Premises và Semesters.

### Question Review Workspace

- Chuyển từ bảng có nhiều nút lặp lại sang luồng preview-first.
- Click câu hỏi mở drawer bên phải với nội dung, A/B/C/D, đáp án đúng, giải thích, source evidence, concept/family và metadata.
- Action chính đặt trong drawer: duyệt, từ chối, sửa.
- Row chỉ giữ `Xem`, action ngữ cảnh và overflow menu.
- Bulk action chỉ xuất hiện sau khi có selection.
- Keyboard: `J/K` câu trước/sau, `A` duyệt, `R` từ chối, `E` sửa, `Esc` đóng.
- Loại notice trùng và bỏ CTA “Duyệt hết câu chờ” khỏi header.

### Người dùng & phân quyền

- Bỏ hero/card-wall theo vai trò.
- Trang chuyển sang danh sách quyền theo người dùng, vai trò, phạm vi, trạng thái và người cấp.
- Panel gán quyền compact hiển thị role description và preview hiệu lực.
- SYSTEM_ADMIN hiển thị đúng “Quản trị toàn hệ thống / Không giới hạn phạm vi”.
- Import Excel vẫn là công cụ phụ, không chiếm bố cục chính.
- Backend RBAC và scope enforcement không thay đổi.

### Các chỉnh sửa khác

- Analytics ánh xạ network/403/404 error thành thông báo tiếng Việt; không lộ raw `Failed to fetch`.
- Premises và Semesters dùng `EnterpriseDataTable`; xóa được đưa vào overflow menu.
- Student/Teacher table rút gọn nội dung và ưu tiên cột có giá trị quyết định.
- Jobs/Audit table giảm độ rộng cột số, ngày, trạng thái và ẩn cột phụ theo priority.
- AP Sync CTA không còn kéo full-width toàn màn hình.
- Settings input có chiều rộng đọc được thay vì kéo hết viewport.

## Không thay đổi

- Không thêm Bootstrap/React-Bootstrap.
- Không thay API contract, URL state hoặc server-side pagination/filter/sort.
- Không thay Bank hierarchy, Release/Quiz semantics, AP/CMS sync, analytics pipeline hoặc Celery.
- Không khôi phục Assignment score write.
- Không có migration mới; latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.

## Phần còn lại của roadmap UI

`.64.16.1` hoàn thành foundation và các workspace ưu tiên. Các phase sau tiếp tục migrate sâu Quiz, Student/Teacher detail, Analytics, Ops/Settings theo cùng contract; không quay lại redesign shell lần nữa.
