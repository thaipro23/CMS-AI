# Class analytics 503 and explicit score refresh

## Scope and history

- CMS-AI base: `27504d1`; prior retry/concurrency changes remain unchanged.
- CMS-FPT base: `5c7887a` (`fpt-indigo-ui`).
- Both fixes use branch `fix/score-refresh-503-20261012`.
- The earlier `b7fdfc7` Unit Reset patch is NOT a parent of the new CMS-FPT fix.
  No Unit Reset files, grade reconciliation tasks or reset migrations are included.

## Changes

1. Class analytics observes existing ItemBank selections without randomizing,
   saving learner state or emitting selection events. Normal LMS requests keep
   their existing selection behavior.
2. The optional official-progress helper cannot execute SQL outside the replica.
   Refused SQL permits explicitly labelled progress fallback instead of discarding
   independently read grades. Real replica/configuration/database failures still
   fail the request. No guard is relaxed for component-grade queries.
3. Missing subsection grades are supplemented from the existing StudentModule
   collector by usage key. Valid persisted grades, including zero, remain
   authoritative. ItemBank fallback uses only valid saved selections with all
   selected problem scores present; historical deselected questions are excluded.
   Missing/stale selection prevents recovery of the entire affected subsection.
   No grade or learner state is written in LMS.
4. Component lists are no longer truncated at 80 in Connector or Dash.
5. The score-update button waits for account/enrollment jobs, then requests a
   forced learning sync. Only an already-running forced learning sync satisfies
   the action; a partial learning sync does not.

## Verification

- Connector unit suite: 39 passed, including actual Django database guard tests.
- Read-only selection policy: 5 passed.
- Targeted backend score/contract/retry/job tests: 41 passed.
- Frontend actual action tests: 7 passed (`npm run test:score-refresh`).
- Frontend TypeScript: `tsc --noEmit` passed.
- Regression fixture: 16 Quiz + Final with full marks replaces an old 6.3/10
  snapshot with 10/10; weighted LMS 200% is retained as raw source data, not used
  as Dash's overall score.
- Broad backend run stopped at 8 failures after 267 passes and 12 skips.
  Every failing case also fails on unchanged `27504d1`: Postgres migration/Redis
  smoke prerequisites, two teacher branch-isolation cases, two older bank UI
  assertions, and two question-bank workflow fixture cases.
- Full Open edX transformer/runtime integration and production PH56940 payload
  have NOT been verified in this environment.

## Deployment and acceptance

Build Open edX from the NEW CMS-FPT fix, not the reset branch. Expected connector
runtime: `25.9.16.5.108`; package: `0.1.18`. Build Dash frontend/backend/worker
from the CMS-AI fix. No new database migration is required by this patch.

Do not reset Quiz, change MySQL points, purge queues/cache, or repair snapshots
manually to validate this issue.

Validate one class first, with PH56940 / Open edX user 20787 /
`course-v1:FPL+DOM1021+FA26`:

1. Confirm all LMS pods use the same new image and Connector runtime version.
2. Request class analytics and record HTTP status and the 17 component grades.
3. Click score update; verify the completed job is `learning_sync`, `force=true`.
4. Compare returned component names/usage keys/points with persisted Dash payload,
   `learning_synced_at`, and the class API/UI. Quiz 5 and 6 must be present with
   their actual source scores, not planned shells.
5. Check fallback `source`/`fallback_reason` separately from grade data. A fallback
   progress percentage is not an official Course Home percentage.

These tests prove specific code defects and recovery behavior. They do not prove
that every production 503 or PH56940's currently missing grades are resolved
until the deployed end-to-end trace above has been checked.
