# Daily pipeline stuck at 1% after coordinator lock contention

The production root `83472a84-c5b9-40bd-9133-0524d10373be` remained at 1%
with no AP attempt recorded. Logs at 01:00, 03:00, 05:00, 07:00 and 09:00
Vietnam time showed the worker immediately returning `coordinator_busy`
before the start/recovery publisher released its coordinator lock. Celery
reported SUCCESS, but no continuation was confirmed. The 7200-second
confirmation lease repeated the same lost-wakeup sequence every two hours.

## Change

- Prepare and commit a durable continuation while holding the coordinator;
  defer actual root-task publication until Redis, PostgreSQL and process locks
  and the coordinator session have all been released.
- Store an intent UUID and refetch the parent under a row lock after broker I/O.
  Update only the matching pending intent on an active parent. Fast worker
  confirmation, newer intent and terminal state are never overwritten.
- Leave unflushed intents immediately due so watchdog can recover process
  death. Keep the broker failure budget until publication actually succeeds.
- Retry coordinator contention after 30 seconds on the same Celery root task.
  This does not create business attempts or advance stage retry rounds.
- Enforce the existing 24-hour root deadline in the worker as well as watchdog,
  before any AP or downstream stage starts. Propagate expiry to scope parents.

The optional deferred mode is used only by daily root operations (start,
recovery, resume and continuation). Other scheduled-parent callers still
publish synchronously. Course/grade rules and pipeline stages are unchanged.
No database migration or frontend/MFE/CMS-FPT rebuild is required.

## Verification

- Six original regression failures reproduced lock-held publication, missing
  contention retry and fast-consumer state overwrite before the fix.
- Deadline regression also failed before the worker expiry check was added.
- 89 focused tests passed across daily AP/mapping, provisioning, score,
  reports, scheduling, recovery and the nine new delivery tests.
- Full backend suite: 1158 passed, 15 skipped, 313 failed. The failed test names
  exactly match the fresh pre-change run (1149 passed, 14 skipped, 313 failed).
  The existing named failure list is QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt.
- Changed production modules/new test pass F401/F821/E9 checks and diff checks.
- Real Redis integration: 4 passed, 2 skipped (PostgreSQL service unavailable).
  The new immediate-consumer case failed against the original production code
  and passed after restoring the fix; it verifies the worker can acquire the
  coordinator after publication and its acknowledgement survives.
- Independent review found no blocking issue. PostgreSQL contention and live
  deployment acceptance remain to be verified outside the local tests.

## Deployment and resuming the current root

Build/deploy the CMS-AI backend, Celery workers and beat consistently from this
fix on `feat/import-quiz-cms-old-su26`. Implementation did not deploy production
or enqueue its jobs. Once the new image is running, enqueue the existing root
once; do not create another daily run or clear Redis/database state:

```bash
kubectl -n openedx exec -i deploy/ai-server-backend -- python - <<'PY'
from app.worker import celery_app
task = celery_app.send_task(
    'academic_daily_pipeline_task',
    args=['83472a84-c5b9-40bd-9133-0524d10373be'],
    queue='sync-fast',
)
print('TASK_ID:', task.id)
PY
```

Verify the root advances beyond 1%, records AP attempts and then reaches
mapping/provision/score/report stages. A genuinely busy coordinator must log
RETRY rather than terminal SUCCESS/coordinator_busy. This root's 24-hour
deadline is still enforced; a late resume is rejected rather than restarting
expired work. The existing confirmation timeout remains unchanged.
