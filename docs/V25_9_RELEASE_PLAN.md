# v25.9 - Repair, Diversity, Publish Verification & Regression Guard

## v25.5 Draft Error Reason & Repair Center
- `draft_error` now stores `draft_error_reason`, `draft_error_detail`, `duplicate_score`, and `repair_attempt_count`.
- Question cards show why a draft is blocked.
- New actions: `Repair` and `Keep anyway`.
- Backend randomizes answer positions after generation so the correct answer is not always A.

## v25.6 Smart Duplicate & Question Diversity
- Added diversity report endpoint: `GET /api/question-bank/diversity/report?course_id=...`.
- Groups repeated concepts and near-duplicate questions.
- Question Bank has a Diversity button for quick inspection.

## v25.7 Publish Verification
- Added dry-run publish endpoints:
  - `POST /api/publish/questions/{question_id}/openedx/dry-run`
  - `POST /api/publish/courses/{course_id}/openedx/dry-run`
- Publish now stores `publish_status`, `publish_verification_json`, and `published_by`.

## v25.8 Real Open edX Connector Test
- Added admin Settings endpoint: `POST /api/settings/openedx/test?course_id=...`.
- Settings page has `Test Open edX` button.

## v25.9 Regression Guard
- Added regression tests for:
  - Largest Remainder Method
  - answer randomizer
  - quality error code
  - diversity report

## Run
```bat
docker compose down
docker compose up --build
```

If schema is stale:
```bat
docker compose down -v
docker compose up --build
```
