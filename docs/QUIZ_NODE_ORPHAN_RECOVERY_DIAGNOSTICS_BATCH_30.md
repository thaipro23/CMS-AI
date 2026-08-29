# Batch 30 — Quiz node orphan recovery and diagnostics

## Symptom

`question_bank.release.quiz.create.async` fails with HTTP 400, `invalid_quiz_node_request`, phase `create_quiz_node.validation`, while production hides the exact `ValueError`.

## Root cause

Batch 27 correctly stopped reusing an existing Quiz node by display name, preventing repeated creation from accumulating questions. However, `create_quiz_node` creates the hierarchy step by step. If a request fails after a chapter/sequential is created but before the endpoint returns a leaf usage key, AI Server cannot invoke compensation because it never received `created_node_id`. The empty shell remains in Studio. A retry sees the same display name and the strict duplicate guard raises `ValueError`, returned as generic HTTP 400.

## Fix

- Stable idempotency key per Course + chapter mapping + assessment type.
- Reuse an existing node only when its block ID matches the idempotency key.
- Recover legacy partial nodes only when the whole matching hierarchy is empty.
- Never reuse a node that already contains Problem Bank or other content.
- Return HTTP 409 `quiz_node_conflict` with safe existing-node details for real conflicts.
- Return a `request_id` and write it to CMS logs for all create-Quiz validation/runtime failures.

## Deployment

Backend/worker and `openedx-ai-connector` CMS plugin must be updated. No database migration and no frontend/MFE build are required.

Connector package version: `openedx-ai-connector 0.1.7`.
