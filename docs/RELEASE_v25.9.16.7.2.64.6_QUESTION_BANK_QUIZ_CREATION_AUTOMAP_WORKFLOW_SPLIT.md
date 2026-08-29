# v25.9.16.7.2.64.13 — Question Bank Quiz Creation/Auto-map Workflow Split

## Mục tiêu

Tách workflow tạo Quiz/Final test từ Bank Release, preview/apply auto-map Course CMS và native Problem Bank creation khỏi `question_bank_service.py` sang module riêng.

## Thay đổi chính

- Thêm `backend/app/services/question_bank/quiz_creation.py`.
- Thêm `QuestionBankQuizCreationWorkflowService`.
- `VersionedQuestionBankService` giữ public methods cũ và delegate sang workflow mới.
- Tách nhóm method:
  - `preview_quiz_auto_map`
  - `apply_quiz_auto_map`
  - `_build_release_quiz_plan`
  - `preview_quiz_from_release`
  - `create_quiz_from_release`
  - các helper action/status/mapping liên quan.
- `MaintainabilityContractService` theo dõi module mới.

## Safety

Không đổi route/API response shape, không đổi semantics publish/release, không đổi cách gọi Open edX connector. Đây là behavior-preserving workflow split.

## Migration

Không có migration mới. Latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
