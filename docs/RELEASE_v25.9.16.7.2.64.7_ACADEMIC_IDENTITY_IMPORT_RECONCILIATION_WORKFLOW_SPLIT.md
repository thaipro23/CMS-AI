# v25.9.16.7.2.64.12 — Academic Identity Import/Reconciliation Workflow Split

## Mục tiêu

Tiếp tục tách `academic_service.py` theo workflow, lần này đưa RollNumber identity reconciliation, cleanup UAT có kiểm soát, migration assistant và manual Open edX mapping import sang module riêng.

## Thay đổi chính

- Thêm `backend/app/services/academic/identity.py`.
- Thêm `AcademicIdentityReconciliationWorkflowService`.
- `AcademicService` delegate các method identity reconciliation/import cũ sang workflow mới.
- Giữ nguyên response shape và semantics của RollNumber policy.
- Bổ sung binding cho các function đã tách trong `academic/sync_enrollment.py` để bảo toàn bound-method semantics runtime.
- Cập nhật `MaintainabilityContractService` để theo dõi workflow mới.

## Safety

- Không đổi Open edX connector behavior.
- Không đổi route/API contract.
- Không đổi Student Ops access boundary.
- Không đổi cleanup guard: destructive cleanup vẫn cần env/confirm phrase.
- Không có migration mới.
