# v25.9.16.7.2.64.13 — Academic Sync/Enrollment Mutation Workflow Split

## Mục tiêu

Tách workflow mutation CMS/Open edX ra khỏi `academic_service.py` mà không đổi public API contract.

## Thay đổi chính

- Thêm `backend/app/services/academic/sync_enrollment.py`.
- Thêm `AcademicSyncEnrollmentWorkflowService`.
- `AcademicService` delegate các workflow:
  - `_student_cms_username`
  - `_student_cms_email`
  - `_student_cms_payload`
  - `_upsert_teacher_cms_metadata`
  - `resolve_class_openedx_users`
  - `_upsert_enrollment_snapshot`
  - `sync_class_course_enrollment`
  - `sync_class_learning_insight`
  - `_try_auto_map_course_for_class`
  - `sync_class_full_cms_flow`
- Cập nhật maintainability contract để theo dõi module mới.

## Safety

- Không thay đổi route/API response shape.
- Không thay đổi rule sync/enroll/pull learning insight.
- Không thêm migration.
- Không rewrite Open edX publish/enrollment semantics.
- Không đổi Student Ops access boundary đã tách ở `.64.2`.

## Migration

Không có migration mới. Latest remains `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
