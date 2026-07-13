# v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split

## Mục tiêu

Tách phần AP sync/import orchestration khỏi route học vụ và bỏ luồng nhập/sửa điểm Assignment trên AI Server vì điểm Assignment do hệ thống khác xử lý.

## Backend

- Thêm `backend/app/services/academic/ap_sync.py` với `AcademicAPSyncWorkflowService`.
- Route `backend/app/api/routes/academic.py` delegate các luồng AP sync/options/import/job sang workflow mới.
- Thêm `backend/app/services/academic/assignment_external.py` với read-only facade cho assignment score snapshot và hard-block write.
- `PUT /api/academic/classes/{class_id}/assignment-defense-scores` trả HTTP 410 `ASSIGNMENT_SCORE_EXTERNALIZED`.
- Bỏ quyền `academic.manage_assignment_scores` khỏi business RBAC; `can_manage_assignment_scores_for_campus()` luôn `False`.

## Frontend

- `/student-management/classes/{classId}` không còn hiện nút `Workflow Assignment`.
- UI hiển thị nhãn `Assignment: đọc từ hệ thống ngoài`.
- App permission map bỏ `manage_assignment_scores`.

## Safety

- Không có migration mới.
- Không đổi AP sync semantics, Celery task, AcademicImportService hoặc response shape.
- Không xóa dữ liệu assignment score cũ; chỉ tắt nhập/sửa từ AI Server.
