# ADR 0001: Split review status from Open edX lifecycle status

## Decision

Keep `ai_questions.status` as the teacher/review workflow field and add explicit Open edX lifecycle fields:

- `openedx_publish_status`
- `openedx_verification_status`
- `openedx_delete_status`
- `openedx_manual_action_required`

## Reason

The old `status='published'` could mean multiple things: imported, verified, pending manual Studio publish, or needing manual delete after rollback. That ambiguity made dashboards and rollback decisions unsafe.

## Consequences

Legacy UI can keep reading `status` and `publish_status`, while new UI and analytics should prefer the explicit `openedx_*` fields.
