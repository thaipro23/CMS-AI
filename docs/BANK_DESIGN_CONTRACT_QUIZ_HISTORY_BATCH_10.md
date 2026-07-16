# Bank Design Contract — Quiz, History & Remaining Screens (Batch 10)

## Phạm vi

Chuẩn hóa toàn bộ route thuộc `/bank` theo cấu trúc sáu tầng đã chốt, tập trung chính vào:

- `/bank/quiz`
- `/bank/history`
- `/bank`
- `/bank/search`
- các trang hierarchy và Chapter đã sửa trước đó được đưa về cùng class contract và page identity.

Không thay đổi API, request payload, RBAC, URL state, workflow Release/Quiz hoặc Open edX semantics.

## Design contract dùng chung

Mỗi màn Bank sử dụng:

1. AppShell cố định: sidebar, topbar và main scroll container.
2. Page identity: icon, một `h1`, mô tả ngắn và action/meta tùy chọn.
3. Inline notice nằm riêng giữa identity và nội dung.
4. Workflow/action vùng riêng khi nghiệp vụ cần.
5. Section có header, description, meta/action và body.
6. Filter/table controls/table/pagination giữ chung EnterpriseDataTable contract.

Component mới:

- `BankPageIdentity`
- `BankWorkflowStepper`
- `BankSection`

## `/bank/quiz`

Chuyển Main workspace sang đúng bố cục ảnh đã chốt:

- Page identity rõ ràng.
- Stepper 3 bước đặt riêng phía trên workspace.
- Desktop hai cột:
  - trái: Kết quả map, summary, danh sách bài và trạng thái Section/Release;
  - phải: Cấu hình map gồm Course ID, Version môn, kiểm tra map và lưu cấu hình.
- Lịch sử khóa học là section độc lập phía dưới.
- Empty state của kết quả map có chỉ dẫn và metric placeholder.
- Tablet chuyển một cột, cấu hình map đặt trước kết quả.
- Mobile filter/action/button chuyển một cột; table chỉ cuộn trong table viewport.
- Permission state cũng dùng đúng Page identity và empty state contract.

## `/bank/history`

- Thêm Page identity và action làm mới.
- KPI vẫn giữ nhưng nằm đúng thứ tự sau feedback.
- Quiz và Release dùng tab thống nhất.
- Filter toolbar nằm trong cùng section với bảng.
- Kết quả, density, column visibility và pagination tiếp tục dùng EnterpriseDataTable.

## Các màn Bank còn lại

- `/bank`: thêm Page identity cho Tổng quan.
- `/bank/search`: thêm Page identity, breadcrumb và action quay về Tổng quan.
- Hierarchy/Chapter: `BankHierarchyPageIntro` được chuẩn hóa thành một `h1`, icon dùng flex layout, không absolute.
- Tất cả PageRoot thuộc `/bank` nhận `bank-contract-page` để dùng cùng spacing, section, responsive và notice rules.

## Responsive

- Desktop: workspace Quiz hai cột.
- Dưới 1180px: workspace Quiz một cột, cấu hình map đặt trước.
- Dưới 900px: toolbar và form tự wrap có chủ đích.
- Dưới 680px: section header/action, filter và button chuyển thành grid một hoặc hai cột.
- Dưới 420px: action section và metric chuyển một cột.

## Verification

Theo yêu cầu hiện tại, batch này không chạy:

- TypeScript check
- lint
- unit test
- production build
- browser smoke test
- responsive screenshot test

Cần xác minh trên UAT thật sau khi deploy, đặc biệt ở 1366px, iPad 768/1024px và điện thoại 390px.
