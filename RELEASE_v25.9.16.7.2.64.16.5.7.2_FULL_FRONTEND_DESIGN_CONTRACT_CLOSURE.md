# v25.9.16.7.2.64.16.5.7.2 — Full Frontend Design Contract Closure

## Mục tiêu

Đóng các lỗi UI đã được người dùng review sau `.64.16.5.3` và áp dụng cùng quy tắc cho toàn bộ frontend, thay vì tiếp tục vá từng trang bằng CSS riêng lẻ.

## App shell và điều hướng

- Sidebar và workspace bám viewport; chỉ main content cuộn dọc.
- Bỏ `Tìm kiếm câu hỏi` khỏi sidebar.
- Breadcrumb trong main content trở thành compatibility no-op; topbar là nơi duy nhất sở hữu title/context.
- `PageRoot` tiếp tục không tạo wrapper DOM thừa.
- Thêm `ContextBackLink` dùng chung cho các trang lồng nhau.

## Học kỳ

- `Làm mới` và `Thêm học kỳ` nằm bên phải header `Danh sách học kỳ`.
- Bỏ KPI strip và summary lặp.
- Bảng gồm đúng: STT, Học kỳ, Lịch Block 1, Lịch Block 2, Trạng thái, Thao tác.
- Block editor dùng single-flow responsive, không ép hai khối chồng nhau hoặc tạo cuộn ngang modal.

## Bank

- Dashboard gom preset ngày, khoảng ngày, phạm vi, trạng thái cache và thời điểm cập nhật vào một toolbar responsive.
- Không lặp title/breadcrumb `Ngân hàng câu hỏi` trong content.
- Chapter workspace bỏ primary KPI strip; số còn lại/chờ duyệt/trạng thái chốt được đưa vào action phù hợp.
- `Concept` và `Nguồn` mặc định ẩn nhưng vẫn chọn được từ `Cột hiển thị`.
- Duyệt câu hỏi giữ modal lớn ở giữa màn hình.
- Các trang Department → Subject → Version → Chapter có back action rõ ngữ cảnh.

## Student, Analytics và bảng dữ liệu

- `Tự động ghép Course CMS` chuyển vào section danh sách môn.
- Bảng chi tiết sinh viên chuyển sang `EnterpriseDataTable` với STT, identity, CMS/enrollment/progress/eligibility và component scores.
- Bank Search và bảng phiên học trong Analytics detail cũng dùng table primitive chuẩn.
- `EnterpriseDataTable` mặc định không render summary lặp; cột vẫn hiển thị đầy đủ, wrap nội dung và chỉ container bảng cuộn ngang khi cần.

## Users/RBAC

- Form gán quyền cố định được thay bằng modal giữa màn hình.
- Chọn nhiều phạm vi/môn trong một lần, tìm kiếm server-side, chọn tất cả kết quả đang thấy và preview trước khi xác nhận.
- `CAMPUS_MANAGER` chỉ còn đọc dữ liệu legacy, không được cấp mới.
- Endpoint mới `POST /api/rbac/assignments/batch` validate toàn bộ scope trước khi mutate, loại scope trùng, dùng một transaction và rollback nếu lỗi.
- Không có thay đổi schema database.

## Build UAT

- `FRONTEND_VALIDATE_IN_IMAGE=false` mặc định để không chạy lặp lint/typecheck trong image build; `next build` vẫn bắt buộc.
- `experimental.webpackBuildWorker=false` tránh build worker con bị treo trên host UAT hạn chế.
- Không cần CI/E2E để deploy bản này; CI hiện hữu không nằm trong critical path `docker compose build`.

## Không thay đổi

- Không thêm Bootstrap/jQuery/Metronic.
- Không thay Bank hierarchy/publish semantics.
- Không khôi phục Assignment score write.
- Không reset DB/volume.
- Không có migration mới; Alembic head vẫn là `0053`.
