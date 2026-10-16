# CMS-AI — bản đồ mã nguồn

Rà soát tại `f961e76a6bb269e09d93c52ea52b96e7f5b028a5` (15/10/2026).
Chạy `python scripts/repo_index.py check`; file mới/đổi tra bằng `find` hoặc `ls`.
Đây là điểm vào; không phải danh sách symbol hay bằng chứng deploy.

## Thư mục

| Thư mục | Vai trò |
|---|---|
| `backend/app/api/routes/` | API; mount tại `backend/app/api/router.py` |
| `backend/app/services/academic/` | AP, roster, enrollment, pipeline, báo cáo, email |
| `backend/app/services/question_bank/` | import, generation, review, release, Quiz |
| `backend/app/services/learning_analytics/` | tracking, hành vi học tập và tổng hợp |
| `backend/app/models/`, `backend/app/schemas/` | DB models và API schemas |
| `backend/alembic/versions/` | migration graph; không suy head từ tên file lớn nhất |
| `backend/app/tests/`, `frontend/tests/`, `e2e/tests/` | kiểm thử theo phạm vi |
| `frontend/app/`, `frontend/components/`, `frontend/styles/` | route Next, UI và CSS |
| `deploy/`, `infra/`, `tutor-plugins/` | manifests và tích hợp hạ tầng |
| `openedx-connector-plugin/`, `openedx-unit-reset-plugin/` | bản plugin trong repo AI; đối chiếu CMS-FPT trước đồng bộ |

## Tác vụ → mở đúng file

| Tác vụ | Điểm vào |
|---|---|
| Daily pipeline/continuation/lock | [daily_academic_pipeline](backend/app/services/academic/daily_academic_pipeline.py), [batch_coordinator](backend/app/services/academic/batch_coordinator.py), [worker](backend/app/worker.py) |
| AP/manual campus/assignment | [ap_academic_sync](backend/app/services/ap_academic_sync.py), [ap_importer](backend/app/services/academic/ap_importer.py), [ap_sync](backend/app/services/academic/ap_sync.py) |
| Student identity/enrollment | [identity](backend/app/services/academic/identity.py), [roster](backend/app/services/academic/roster.py), [sync_enrollment](backend/app/services/academic/sync_enrollment.py) |
| Teacher đa hệ, report/cache | [teacher_report](backend/app/services/academic/teacher_report.py), [report_snapshot](backend/app/services/academic/report_snapshot.py), [teacher_report_cache](backend/app/services/academic/teacher_report_cache.py) |
| Điểm và planned assessment | [assessment_components](backend/app/services/academic/assessment_components.py), [component_read_cache](backend/app/services/academic/component_read_cache.py), [openedx_client](backend/app/services/openedx_client.py) |
| Import Quiz cũ SU26 | [legacy_quiz_import](backend/app/services/question_bank/legacy_quiz_import.py), [UI](frontend/app/import-quiz-cms-old/page.tsx) |
| AI quota/manual/import | [question_origin](backend/app/services/question_origin.py), [generation_review](backend/app/services/question_bank/generation_review.py), [ChapterWorkspacePage](frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx) |
| Quiz/Final/publish/context | [quiz_creation](backend/app/services/question_bank/quiz_creation.py), [release_publish](backend/app/services/question_bank/release_publish.py), [fa26_compat](backend/app/services/fa26_compat.py) |
| RBAC/scope/403 | [business_rbac](backend/app/services/business_rbac.py), [academic/access](backend/app/services/academic/access.py), [AppShell](frontend/components/layout/AppShell.tsx) |
| Email nhắc tiến độ | [progress_email](backend/app/services/academic/progress_email.py), [progress_email_delivery](backend/app/services/academic/progress_email_delivery.py) |
| Bảng/cuộn/dialog/CSS | [EnterpriseDataTable](frontend/components/table/EnterpriseDataTable.tsx), [AccessibleDialog](frontend/components/ui/AccessibleDialog.tsx), [layout CSS order](frontend/app/layout.tsx) |
| Analytics ML / dữ liệu thiếu / stale | [feature builders](backend/app/services/learning_analytics/ml_features.py), [scorer](backend/app/services/learning_analytics/ml_anomaly.py), [worker workflow](backend/app/services/learning_analytics/ml_workflow.py), [API presentation](backend/app/services/learning_analytics/ml_presentation.py), [UI card](frontend/components/analytics/MLAnalysisCard.tsx), [offline evaluator](scripts/evaluate-learning-ml.py) |
| Runtime config/CI | [config](backend/app/core/config.py), [Jenkinsfile](Jenkinsfile), [deploy](deploy/) |

Tracking/analytics: `python scripts/repo_index.py ls backend/app/services/learning_analytics`;
test phù hợp: `find "ten_chuc_nang" --prefix backend/app/tests --limit 10`.
Route frontend: `find "page.tsx" --prefix frontend/app --limit 10`, thêm từ khóa route.
Đọc quy tắc và runbook liên quan tại [docs/INDEX.md](docs/INDEX.md).

Bản đồ chi tiết trước đây được lưu tại
[docs/history/CODE_INDEX_2026-09-06.md](docs/history/CODE_INDEX_2026-09-06.md);
các nhận định/kiểm thử trong đó chỉ thuộc mốc lịch sử.
