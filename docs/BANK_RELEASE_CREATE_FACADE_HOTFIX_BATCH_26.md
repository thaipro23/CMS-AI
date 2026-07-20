# Batch 26 — Bank Release create facade hotfix

## Symptom

Clicking **Chốt bộ đề** returned HTTP 500 before a Release was created.

## Root cause

`POST /api/question-bank-v2/releases` forwards every field from `BankReleaseCreate`:

- `bank_version_id`
- `release_code`
- `title`
- `include_approved_questions`
- `force`

The `VersionedQuestionBankService.create_release` facade only accepted
`bank_version_id`, `title`, and `actor`. Python therefore raised an unexpected
keyword `TypeError` before the extracted release workflow could run. The public
error mapper correctly classified that unexpected defect as HTTP 500.

## Fix

The facade now accepts and forwards the complete API/workflow contract. A static
regression test protects the signature from drifting again. No database migration
is required.

## Deployment

Rebuild/recreate `backend`. `worker` does not execute the synchronous Release
creation call, but rebuilding it together is safe when using a shared backend
image.
