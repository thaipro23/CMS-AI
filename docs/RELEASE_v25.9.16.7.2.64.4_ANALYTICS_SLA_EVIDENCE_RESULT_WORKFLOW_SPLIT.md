# v25.9.16.7.2.64.13 — Analytics SLA/Evidence/Result Workflow Split

## Mục tiêu

Tách các workflow analytics đọc/hiển thị khỏi `backend/app/services/learning_analytics/analytics_core_service.py` theo hướng behavior-preserving, không đổi route/API và không đụng vào ingest/recalculate mutation pipeline.

## Module mới

- `backend/app/services/learning_analytics/operations.py`
  - `analytics_sla_report`
  - `pilot_acceptance_report`
  - `analytics_uat_evidence_pack`
- `backend/app/services/learning_analytics/results.py`
  - `learning_dashboard`
  - `export_learning_behavior_csv`
  - `video_students`
  - `student_behavior_detail`
  - `class_behavior_overview`
  - `analytics_course_class_mapping_reliability_report`
  - `class_result_doctor`
  - `behavior_summary`
  - `behavior_rows`

## Giữ nguyên behavior

`LearningAnalyticsCoreService` vẫn giữ public method cũ và delegate sang workflow mới. Low-level helpers như `_course_for_class`, `_class_student_roster`, `_apply_behavior_common_filters`, `_class_course_mapping_diagnostics` vẫn ở core để tránh rewrite sâu khi chưa có integration test đầy đủ.

## Không đổi

- Không có migration mới.
- Không đổi ingest tracking log.
- Không đổi recalculate worker.
- Không đổi wording tín hiệu mềm.
- Không đổi route/API response shape.
