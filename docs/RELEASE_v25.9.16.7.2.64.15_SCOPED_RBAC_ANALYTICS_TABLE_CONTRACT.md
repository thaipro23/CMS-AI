# v25.9.16.7.2.64.15 — Scoped RBAC + Analytics Workspace Stabilization + Unified Table Contract

## Mục tiêu

Sửa các vấn đề UAT thực tế của `.64.14`: request storm/403 tại Analytics, bảng lệch cột và khoảng trống sticky, workflow identity không còn cần thiết, cùng RBAC chưa phản ánh đúng cây trách nhiệm nghiệp vụ.

## Thay đổi chính

### Analytics workspace

- Thêm endpoint read-only `GET /api/analytics/classes/{class_id}/workspace`.
- Endpoint xác thực quyền lớp một lần rồi trả `summary`, `rows`, `doctor` và `permission_scope`.
- Frontend dùng một request workspace thay cho ba request độc lập.
- Pilot acceptance, evidence pack, release candidate, pilot operations và các gate vận hành không còn tự tải khi chỉ xem kết quả.
- Chỉ người có `ops.readiness.view` mới thấy và tải vùng kiểm tra vận hành.
- Teacher/AP-assigned là read-only; recalculate tiếp tục yêu cầu quyền quản lý đào tạo.

### Unified table contract

- `EnterpriseDataTable` tự tính sticky offset từ các cột đang hiển thị.
- Thêm `colgroup` để header/body dùng cùng hình học.
- Cột STT chuẩn hóa 64 px và căn giữa.
- Selection column chuẩn hóa 52 px.
- Tất cả sticky left/right dùng CSS variable offset thống nhất.
- Bảng legacy quan trọng nhận chung geometry/scroll contract để giảm khác biệt trong khi chưa migrate toàn bộ sang component mới.

### Identity workflow

- Xóa panel `Kiểm tra identity CMS/RollNumber` khỏi trang chi tiết lớp.
- Xóa các request reconciliation/cleanup khỏi frontend.
- Không chạy cleanup hoặc reset dữ liệu tự động.
- Backend compatibility API vẫn giữ để tránh phá client cũ; có thể loại bỏ ở major cleanup sau UAT.

### Scoped RBAC

- `SYSTEM_ADMIN`: toàn quyền.
- `DEPARTMENT_HEAD`: full quyền nghiệp vụ trong Department được gán và mọi Subject/Offering/Chapter bên dưới.
- `SUBJECT_OWNER`: full quyền nghiệp vụ trong Subject được gán và nhánh dưới.
- `QUESTION_REVIEWER`: chỉ các permission được gán, trong scope và nhánh dưới.
- `CAMPUS_OWNER`: xem/quản lý phạm vi lớp thuộc campus được gán.
- `TEACHER_ASSIGNED`: quyền xem được suy ra động từ AP teacher assignment; chỉ xem lớp được phân công.
- `/rbac/me` trả effective permission, assignment scope và cờ system admin cho frontend.
- Sidebar, route entry và action button dùng permission/scope tương ứng; backend vẫn enforce cuối cùng.

### Runtime gate packaging

- Backend/worker/beat production image dùng `backend/Dockerfile.prod` với build context ở project root.
- Image chỉ copy source cần cho static checks vào `/source-contract`; `.env`, secret, certificate, cache và `node_modules` bị loại bởi `.dockerignore`.
- `UxAcceptanceService`, `SecurityAttackSimulationService` và `MaintainabilityContractService` đọc `SOURCE_CONTRACT_ROOT`.
- Kết quả kiểm tra source artifact: UX `READY 24/24`, security attack static `READY 20/20`, maintainability `READY_WITH_WARNINGS` với 0 blocker và 6 cảnh báo large-file kế thừa.
- Các gate vẫn read-only: không query DB, không gọi external service, không enqueue hoặc mutate dữ liệu.

### Performance readiness index

- Khai báo `ix_academic_classes_scope_lookup` trong SQLAlchemy model metadata.
- Không thêm migration mới vì migration `0050` đã tạo index này và PostgreSQL UAT đã xác nhận tồn tại.

## Database

Không có migration `0053`. Head vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Boundary không thay đổi

- Không thay Bank hierarchy.
- Không thay Release/Quiz publish semantics.
- Không khôi phục Assignment score write.
- Không tự clear/reset database.
- Không nới quyền chỉ ở frontend.
