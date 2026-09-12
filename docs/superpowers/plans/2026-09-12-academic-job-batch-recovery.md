# Academic Job Batch Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover orphaned academic jobs, repair teacher-report exports, and replace the 3,000-job Auto-map fan-out with a durable four-child dispatch window.

**Architecture:** A focused job-runtime service owns enqueue metadata and lease expiry. The Auto-map parent persists its authorized targets and repeatedly fills a bounded child window; deterministic child keys make continuation/redelivery idempotent. Teacher exports reuse only complete, fresh replica snapshots and otherwise perform the existing connector refresh.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL advisory locks, Alembic, Celery/Redis, pytest, Next.js/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-12-academic-job-batch-recovery-design.md`

## Global Constraints

- Keep ordinary reports and exports on replica-backed snapshots.
- Use primary only for the immediate read after enrollment.
- Keep the complete Auto-map workflow: mapping, account provisioning, CMS staff verification, enrollment, then learning sync.
- Process only the class IDs captured in the authorized enqueue-time scope.
- Default active child window is four and must be bounded to 1–20.
- Preserve job rows for audit; recovery changes status and never deletes history.

---

### Task 1: Academic job runtime primitives

**Files:**
- Create: `backend/app/services/academic/job_runtime.py`
- Create: `backend/app/tests/test_academic_job_runtime.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.env.production.example`

**Interfaces:**
- Produces: `enqueue_job_task(task, job_id: str, *, queue: str, attempt: int = 1) -> dict[str, Any]`.
- Produces: `persist_enqueue_metadata(job: Any, metadata: dict[str, Any]) -> None`.
- Produces: `reconcile_stale_rows(rows: Iterable[Any], *, now: datetime, queued_timeout_seconds: int, running_timeout_seconds: int, active_parent_ids: set[str] | None = None) -> list[Any]`.

- [ ] **Step 1: Write failing unit tests for enqueue metadata and lease expiry**

```python
def test_running_job_past_lease_is_marked_failed():
    job = FakeJob(status='running', updated_at=NOW - timedelta(seconds=601))
    changed = reconcile_stale_rows([job], now=NOW, queued_timeout_seconds=900, running_timeout_seconds=600)
    assert changed == [job]
    assert job.status == 'failed'
    assert job.result_json['code'] == 'CELERY_JOB_ORPHANED'

def test_enqueue_metadata_contains_queue_and_task_id():
    meta = enqueue_job_task(FakeTask('task-123'), 'job-1', queue='sync')
    assert meta['queue'] == 'sync'
    assert meta['celery_task_id']
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && pytest -q app/tests/test_academic_job_runtime.py`
Expected: FAIL because `app.services.academic.job_runtime` does not exist.

- [ ] **Step 3: Implement the runtime service and settings**

```python
def enqueue_job_task(task, job_id: str, *, queue: str, attempt: int = 1) -> dict[str, Any]:
    task_id = f'{task.name}:{job_id}:{attempt}:{uuid.uuid4()}'
    result = task.apply_async(args=[job_id], task_id=task_id, queue=queue)
    return {'task_name': task.name, 'celery_task_id': result.id, 'queue': queue,
            'attempt': attempt, 'enqueued_at': datetime.utcnow().isoformat()}
```

Add validated settings for dispatch window `4`, continuation delay `10`, queued lease `900`, class lease `2400`, bulk lease `600`, report lease `6300`, and export snapshot age `300` seconds.

- [ ] **Step 4: Run tests and config validation**

Run: `cd backend && pytest -q app/tests/test_academic_job_runtime.py app/tests/test_v25_9_16_7_2_64_16_5_7_1_uat_http_env_compatibility.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/academic/job_runtime.py backend/app/tests/test_academic_job_runtime.py backend/app/core/config.py .env.example .env.production.example
git commit -m "fix: add durable academic job runtime"
```

### Task 2: Durable child identity

**Files:**
- Create: `backend/alembic/versions/0065_academic_job_batch_recovery.py`
- Modify: `backend/app/models/academic.py`
- Create: `backend/app/tests/test_academic_job_batch_schema.py`

**Interfaces:**
- Produces: `AcademicClassSyncJob.parent_job_id: str | None`.
- Produces: `AcademicClassSyncJob.idempotency_key: str | None` with a unique database constraint.

- [ ] **Step 1: Write the schema contract test**

```python
def test_class_sync_job_has_parent_and_idempotency_columns():
    columns = AcademicClassSyncJob.__table__.columns
    assert 'parent_job_id' in columns
    assert 'idempotency_key' in columns
    assert any(c.unique for c in columns if c.name == 'idempotency_key')
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd backend && pytest -q app/tests/test_academic_job_batch_schema.py`
Expected: FAIL because both columns are absent.

- [ ] **Step 3: Add model columns and idempotent Alembic migration**

```python
parent_job_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
```

The migration uses inspector checks before adding columns/indexes so a partially applied production migration can be rerun safely.

- [ ] **Step 4: Run schema and migration-chain tests**

Run: `cd backend && pytest -q app/tests/test_academic_job_batch_schema.py`
Expected: PASS with Alembic head `0065_academic_job_batch_recovery`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/academic.py backend/alembic/versions/0065_academic_job_batch_recovery.py backend/app/tests/test_academic_job_batch_schema.py
git commit -m "fix: add idempotent bulk child identity"
```

### Task 3: Repair teacher export and orphan recovery

**Files:**
- Modify: `backend/app/services/academic/teacher_report.py`
- Modify: `backend/app/services/academic_service.py`
- Modify: `backend/app/api/routes/academic.py`
- Modify: `backend/app/worker.py`
- Create: `backend/app/tests/test_teacher_report_job_recovery.py`

**Interfaces:**
- Extends: `refresh_training_teacher_learning_data(..., max_snapshot_age_seconds: int = 0) -> dict[str, Any]`.
- Produces: `_teacher_report_class_snapshot_is_fresh(cls, course_id: str, max_age_seconds: int) -> bool`.

- [ ] **Step 1: Write failing tests for the missing argument, fresh reuse, stale expiry, and broker failure**

```python
def test_refresh_contract_accepts_snapshot_age(workflow, user):
    result = workflow.refresh_training_teacher_learning_data(
        user, term_id='term-1', max_snapshot_age_seconds=300,
    )
    assert 'snapshot_reused_class_count' in result

def test_old_running_export_is_failed_before_active_reuse(db, old_job):
    reconcile_teacher_report_jobs(db, now=old_job.updated_at + timedelta(seconds=6301))
    assert old_job.status == 'failed'
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && pytest -q app/tests/test_teacher_report_job_recovery.py`
Expected: FAIL on the unsupported `max_snapshot_age_seconds` argument and missing reconciler.

- [ ] **Step 3: Thread the argument, validate snapshot completeness, and reconcile before list/get/enqueue**

```python
if max_snapshot_age_seconds > 0 and self._teacher_report_class_snapshot_is_fresh(
    cls, course_id, max_snapshot_age_seconds,
):
    snapshot_reused += 1
    progress_callback(index, total, f'Dùng snapshot mới nhất: {cls.class_code or cls.id}')
    continue
```

Use `enqueue_job_task(..., queue='exports')`; on exception mark the new report job failed, commit, and return HTTP 503.

- [ ] **Step 4: Run report tests and verify GREEN**

Run: `cd backend && pytest -q app/tests/test_teacher_report_job_recovery.py app/tests/test_v25_9_16_7_2_64_16_5_7_2_15_teacher_report_freshness_policy.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/academic/teacher_report.py backend/app/services/academic_service.py backend/app/api/routes/academic.py backend/app/worker.py backend/app/tests/test_teacher_report_job_recovery.py
git commit -m "fix: recover orphaned teacher report jobs"
```

### Task 4: Bounded Auto-map coordinator

**Files:**
- Modify: `backend/app/worker.py`
- Modify: `backend/app/api/routes/academic.py`
- Create: `backend/app/tests/test_academic_auto_map_batch_coordinator.py`

**Interfaces:**
- Extends: `_enqueue_academic_class_sync_child_job(..., parent_job_id: str) -> tuple[AcademicClassSyncJob, bool]`.
- Produces: `_bulk_child_idempotency_key(parent_job_id: str, class_id: str) -> str`.
- Produces: `_schedule_bulk_continuation(db, job, *, attempt: int) -> dict[str, Any]`.

- [ ] **Step 1: Write failing tests for window size, continuation, redelivery, and partial failure**

```python
def test_coordinator_dispatches_at_most_four_children(batch_fixture):
    run_auto_map_coordinator(batch_fixture.parent_id)
    assert batch_fixture.active_child_count() == 4
    assert batch_fixture.parent.status == 'running'

def test_redelivery_reuses_parent_class_child(batch_fixture):
    run_auto_map_coordinator(batch_fixture.parent_id)
    run_auto_map_coordinator(batch_fixture.parent_id)
    assert batch_fixture.child_count_for('class-1') == 1
```

- [ ] **Step 2: Run coordinator tests and verify RED**

Run: `cd backend && pytest -q app/tests/test_academic_auto_map_batch_coordinator.py`
Expected: FAIL because the current task fan-outs every class.

- [ ] **Step 3: Replace eager fan-out with persisted dispatch state**

```python
active = [child for child in children if child.status in {'queued', 'running'}]
slots = max(0, settings.academic_bulk_sync_dispatch_window - len(active))
for class_id in undispatched_class_ids[:slots]:
    _enqueue_academic_class_sync_child_job(..., parent_job_id=job.id)
if terminal_count < len(target_class_ids):
    _schedule_bulk_continuation(db, job, attempt=continuation_attempt + 1)
```

The first invocation performs mapping and persists only authorized targets. Later invocations skip mapping, reconcile children, fill slots, update progress, and complete only when all targets are terminal.

- [ ] **Step 4: Run coordinator, RBAC, and primary-read tests**

Run: `cd backend && pytest -q app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_ap_platform_resync_and_class_audit_regression.py app/tests/test_primary_after_enrollment_policy.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/app/api/routes/academic.py backend/app/tests/test_academic_auto_map_batch_coordinator.py
git commit -m "fix: batch auto map class synchronization"
```

### Task 5: Jobs UI recovery actions

**Files:**
- Modify: `backend/app/api/routes/academic.py`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/jobs/page.tsx`
- Modify: `frontend/app/teacher-management/TeacherManagementPlatformPage.tsx`
- Create: `backend/app/tests/test_academic_job_retry_api_contract.py`

**Interfaces:**
- Produces: `POST /academic/bulk-operation-jobs/{job_id}/retry`.
- Produces: `POST /academic/training/teachers/report-jobs/{job_id}/retry`.
- Produces frontend API functions `retryAcademicBulkOperationJob` and `retryAcademicTrainingTeacherReportJob`.

- [ ] **Step 1: Write failing API/source contract tests**

```python
def test_retry_routes_and_frontend_actions_exist():
    assert "/bulk-operation-jobs/{job_id}/retry" in ROUTE_SOURCE
    assert "retryAcademicBulkOperationJob" in API_SOURCE
    assert "CELERY_JOB_ORPHANED" in JOBS_PAGE_SOURCE
```

- [ ] **Step 2: Run contract test and verify RED**

Run: `cd backend && pytest -q app/tests/test_academic_job_retry_api_contract.py`
Expected: FAIL because retry endpoints/actions are absent.

- [ ] **Step 3: Add safe retry endpoints and UI actions**

Only `failed` jobs are retryable. Retry resets timestamps/progress, increments `retry_count`, preserves authorized request scope, and enqueues the same durable row. The UI labels orphan failures as worker interruptions and offers one retry action.

```typescript
export async function retryAcademicBulkOperationJob(headers: HeadersInit, jobId: string) {
  return apiFetch<AcademicBulkOperationJob>(`/api/academic/bulk-operation-jobs/${jobId}/retry`, {
    method: 'POST', headers,
  });
}
```

- [ ] **Step 4: Run backend tests and frontend type-check**

Run: `cd backend && pytest -q app/tests/test_academic_job_retry_api_contract.py`
Run: `cd frontend && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/academic.py frontend/lib/api.ts frontend/app/jobs/page.tsx frontend/app/teacher-management/TeacherManagementPlatformPage.tsx backend/app/tests/test_academic_job_retry_api_contract.py
git commit -m "feat: retry interrupted academic jobs"
```

### Task 6: Full verification and deployment handoff

**Files:**
- Modify: `MASTER_CONTEXT_DASH_CMS.md`
- Create: `RUN_ACADEMIC_JOB_BATCH_RECOVERY_2026-09-12.md`

**Interfaces:**
- Consumes all prior tasks; produces operator verification commands and final release evidence.

- [ ] **Step 1: Run the focused regression suite**

Run: `cd backend && pytest -q app/tests/test_academic_job_runtime.py app/tests/test_academic_job_batch_schema.py app/tests/test_teacher_report_job_recovery.py app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_academic_job_retry_api_contract.py app/tests/test_primary_after_enrollment_connector_client.py app/tests/test_primary_after_enrollment_policy.py app/tests/test_cms_staff_policy.py`
Expected: PASS.

- [ ] **Step 2: Run static verification**

Run: `cd backend && ruff check app/services/academic/job_runtime.py app/services/academic/teacher_report.py app/services/academic_service.py app/api/routes/academic.py app/worker.py app/tests/test_academic_job_runtime.py app/tests/test_academic_job_batch_schema.py app/tests/test_teacher_report_job_recovery.py app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_academic_job_retry_api_contract.py`
Run: `cd backend && python -m compileall -q app`
Run: `cd frontend && npx tsc --noEmit`
Expected: all commands exit 0.

- [ ] **Step 3: Document exact migration, rollout, queue, and UAT commands**

The runbook must verify Alembic head, both worker queue subscriptions, automatic orphan reconciliation, a maximum of four active children, terminal parent progress, and successful Excel download.

- [ ] **Step 4: Commit the handoff**

```bash
git add MASTER_CONTEXT_DASH_CMS.md RUN_ACADEMIC_JOB_BATCH_RECOVERY_2026-09-12.md docs/superpowers/specs/2026-09-12-academic-job-batch-recovery-design.md docs/superpowers/plans/2026-09-12-academic-job-batch-recovery.md
git commit -m "docs: hand off academic job batch recovery"
```

- [ ] **Step 5: Inspect final history and request push authorization if needed**

Run: `git status --short --branch`
Run: `git log --oneline --decorate -12`
Expected: clean worktree with the recovery commits above the approved branch baseline.
