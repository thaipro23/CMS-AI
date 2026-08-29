# v25.9.16.7.2.64.13 — Analytics SLA/Evidence/Result Workflow Split

## Mục tiêu

Tách workflow Release/Publish/Rollback/Audit của Question Bank khỏi `question_bank_service.py` theo từng vùng nghiệp vụ, không đổi contract API/runtime.

## Thay đổi chính

- Thêm `backend/app/services/question_bank/release_publish.py`.
- Thêm `QuestionBankReleasePublishWorkflowService`.
- `VersionedQuestionBankService` giữ public methods cũ nhưng delegate sang workflow mới:
  - `release_readiness`
  - `list_course_quiz_instances`
  - `rollback_course_quiz_instance`
  - `release_library_key`
  - `create_release`
  - `cancel_failed_release`
  - `release_publish_audit`
  - `publish_release_to_openedx`
- `MaintainabilityContractService` theo dõi workflow module mới.

## Safety

Không đổi schema, không đổi route contract, không đổi publish/sync/enrollment runtime semantics. Workflow mới dùng delegation về parent service cho helper thấp tầng để giảm regression khi tách.

## Migration

Không có migration mới. Latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
