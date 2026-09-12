# Academic job batching and orphan recovery

## Purpose

Fix two production failures without changing the approved academic workflow:

- A teacher-report Excel job can remain at a percentage such as 55% forever after its Celery worker is restarted or killed.
- Auto-map Course CMS can create up to 3,000 class-sync rows at once, leaving a large visible backlog in `queued`.

The final workflow remains: map Course CMS, provision student and teacher accounts, verify CMS staff where required, enroll users, and read progress/grades from primary only for the immediate post-enrollment read. Ordinary reports and exports continue to use replica-backed snapshots.

## Confirmed causes

1. Academic job tables treat every `queued` or `running` row as active forever. There is no lease, heartbeat expiry, or orphan reconciliation.
2. The auto-map parent selects classes for both newly mapped and already mapped subjects, then immediately creates one Celery child job for every class up to `max_classes=3000`.
3. The production `sync` worker has concurrency 2, so the fan-out creates a backlog far larger than the worker can drain promptly.
4. Database rows are committed before `.delay()`/`.apply_async()`. A broker error can therefore leave a job permanently queued.
5. The teacher-report worker references `academic_teacher_report_export_snapshot_max_age_seconds`, which is absent from settings, and passes `max_snapshot_age_seconds` through an API that does not accept it.

## Design

### 1. Durable parent coordinator

`AcademicBulkOperationJob` remains the single user-facing parent for Auto-map all. Its `result_json` stores a monotonic coordinator state:

- `phase`: `mapping`, `dispatching`, or `finished`
- `target_class_ids`: the authorized class snapshot after mapping
- `dispatch_cursor`: the next target that has not been materialized
- counts for queued, running, completed, failed, and reused children
- recent child job IDs for diagnostics
- enqueue metadata for the current coordinator iteration

Each coordinator invocation acquires the existing PostgreSQL advisory lock for its parent ID, reloads state, reconciles children, and fills only the available dispatch window. The default window is four active children, configurable with `ACADEMIC_BULK_SYNC_DISPATCH_WINDOW` and bounded to 1–20.

When work remains, the coordinator schedules one continuation after a short configurable interval. The parent remains `running`. When every authorized class has a terminal child state, the coordinator marks the parent `completed`; partial child failures are reported explicitly in its result and label. If no child succeeds, the parent is `failed`.

### 2. Child idempotency

Add nullable `parent_job_id` and `idempotency_key` columns to `academic_class_sync_jobs`. The auto-map key is deterministic from parent ID, class ID, and job type. A unique constraint prevents duplicate children when Celery redelivers a coordinator task or a worker dies between enqueue and cursor persistence.

Normal single-class jobs keep `parent_job_id=NULL` and preserve current behavior. The coordinator reuses an existing child for the same deterministic key regardless of whether it is active or terminal.

### 3. Observable enqueue and failure handling

All three relevant enqueue paths—teacher report, bulk coordinator, and bulk child—use a shared helper that:

- assigns a unique Celery task ID;
- stores task name, queue, task ID, enqueue timestamp, and attempt number;
- catches broker errors;
- changes the durable job to `failed` before returning an HTTP 503 or recording a skipped child.

This prevents a Redis/network error from creating a false `queued` job.

### 4. Orphan reconciliation

Academic job services reconcile active rows before listing, fetching, reusing, or creating jobs. A row is orphaned when its last durable heartbeat is older than its task-specific lease:

- bulk coordinator: 10 minutes;
- class sync: hard limit plus 10 minutes, default 40 minutes;
- teacher report/export: hard limit plus 10 minutes, default 105 minutes;
- never-started queued job: 15 minutes.

Reconciliation marks the row `failed`, sets `finished_at`, and records a public recovery code such as `CELERY_JOB_ORPHANED`. A late Celery message is harmless because every task exits without work when the durable row is no longer `queued` or `running`.

Opening the teacher-management or jobs screen therefore clears the historical 55% row automatically and enables a clean retry. No destructive deletion of audit history is performed.

### 5. Teacher-report contract repair

Add `ACADEMIC_TEACHER_REPORT_EXPORT_SNAPSHOT_MAX_AGE_SECONDS` with a default of 300 seconds and pass it through `AcademicService` to the report workflow.

For an ordinary Excel export, a mapped class can reuse replica-backed snapshots only when every expected roster member has a current-course snapshot within the allowed age and none has a preserved/unknown grade marker. Cache rebuild and forced refresh use an age of zero and perform a live connector refresh. This fixes the current signature/configuration error and avoids repeatedly refreshing a large scope for exports created close together.

### 6. User experience

- Auto-map shows one parent job with class totals and completed/failed progress instead of thousands of waiting rows.
- `/jobs` still allows drilling into the small current child window and completed history.
- Orphaned jobs show a clear worker-disconnected failure rather than an eternal percentage.
- Retrying an orphan creates or requeues one safe parent/report job; it does not duplicate the old operation.

## Error handling and recovery

- A class failure does not stop other authorized classes. The parent records the class and continues.
- A coordinator crash is recovered by Celery late acknowledgement or by orphan reconciliation followed by retry. Deterministic child keys prevent duplication.
- A broker enqueue failure is persisted immediately as failure.
- A scope/RBAC mismatch fails the parent and never widens the saved class list.
- Existing queued/running legacy rows without new metadata are still eligible for age-based orphan reconciliation.

## Testing

Tests are written before production changes and must demonstrate:

1. The current teacher-report call fails because the setting and method argument contract are missing.
2. A fresh export snapshot is reused, while stale/incomplete snapshots trigger refresh.
3. A historical 55% running report becomes failed after lease expiry and no longer blocks a new export.
4. A broker exception marks the just-created job failed.
5. Auto-map never has more active children than the configured window.
6. A continuation advances the cursor and eventually finishes the parent.
7. Redelivery cannot create a second child for the same parent/class.
8. One failed child does not stop the remaining batch.
9. RBAC-approved class IDs remain the maximum processing scope.
10. Existing primary-after-enrollment, CMS staff provisioning, report/export, Ruff, compile, and frontend TypeScript tests remain green.

## Deployment acceptance

After deployment, verify both workers advertise their queues: `ai-server-worker` consumes `interactive,sync`; `ai-server-worker-heavy` consumes `generation,exports`. Opening the affected pages must reconcile the legacy 55% job. A small campus/term run must show no more than four active class jobs, increasing completed counts until the parent reaches a terminal state.
