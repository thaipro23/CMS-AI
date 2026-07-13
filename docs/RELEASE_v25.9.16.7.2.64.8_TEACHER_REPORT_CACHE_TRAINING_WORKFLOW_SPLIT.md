# v25.9.16.7.2.64.13 — Teacher Report Cache/Training Report Workflow Split

## Mục tiêu

Tách workflow báo cáo giáo viên/training-management/cache ra khỏi `academic_service.py` theo hướng behavior-preserving. Không đổi route/API response shape, không đổi quyền Student Ops, không đổi cache semantics.

## Thay đổi chính

- Thêm `backend/app/services/academic/teacher_report.py`.
- Thêm `AcademicTeacherReportWorkflowService`.
- `AcademicService` delegate teacher report cache, lite-fast report, cached report, rebuild cache và training teacher report sang workflow mới.
- Cập nhật maintainability contract tracking.

## Safety

- Không migration.
- Không đổi enrollment/sync/identity/publish/analytics semantics.
- Không đổi response shape `/api/academic/training/teachers`.
- Không đổi worker job rebuild/export teacher report semantics.

## Latest migration

`0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`
