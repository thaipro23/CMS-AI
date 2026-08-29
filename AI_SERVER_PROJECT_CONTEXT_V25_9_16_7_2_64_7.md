# AI Server / Open edX CMS — Context v25.9.16.7.2.64.13

```text
v25.9.16.7.2.64.13 — Academic Identity Import/Reconciliation Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-academic-identity-import-reconciliation-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

## Baseline

Bản `.64.7` tiếp tục từ `.64.6`, không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu

Tiếp tục tách `academic_service.py` theo workflow. `.64.7` tách riêng nhóm RollNumber identity reconciliation/import:

```text
identity reconciliation report theo lớp
UAT identity cleanup có guard
rollnumber identity migration assistant
manual Open edX user mapping import
```

## Thay đổi chính

### Backend

Thêm module:

```text
backend/app/services/academic/identity.py
```

Service mới:

```text
AcademicIdentityReconciliationWorkflowService
```

`AcademicService` giờ delegate các method sau:

```text
_identity_reconciliation_status
identity_reconciliation_for_class
cleanup_identity_reconciliation_for_class
_identity_reconciliation_next_actions
rollnumber_identity_migration_report
import_openedx_user_mappings
```

### Sync enrollment runtime binding fix

Bổ sung binding trong:

```text
backend/app/services/academic/sync_enrollment.py
```

để các function đã tách trước đó hoạt động như bound methods của `AcademicSyncEnrollmentWorkflowService`.

### Maintainability contract

Cập nhật:

```text
backend/app/services/maintainability_contract.py
```

Theo dõi thêm:

```text
backend/app/services/academic/identity.py
```

## Safety

- Không đổi route/API response shape.
- Không đổi Student Ops access boundary.
- Không đổi RollNumber canonical username policy.
- Không đổi Open edX connector behavior.
- Cleanup identity vẫn được guard bằng env/confirm phrase.
- Manual import vẫn dùng `_upsert_mapping(..., source='manual_import')`.
- Không có migration mới.

## Checks đã chạy trong artifact

```text
v64.7-specific tests: 7 passed
selected non-doc regression checks: 21 passed, 4 stale doc-only assertions deselected
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing deps/node_modules/Docker/env or skipped frontend/review
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-academic-identity-import-reconciliation-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Next workflow split candidates

```text
.64.8 — Teacher Report Cache/Training Report Workflow Split
.64.9 — Question Bank Generation/Review Workflow Split
.64.10 — Academic Import/Reconciliation AP Sync Workflow Split
```
