# Academic Job, Daily Report, Email, and Quiz Hardening Design

## 1. Goal

Make the Dash CMS production workflows truthful and replay-safe: a completed job must mean the requested business operation completed for its entire frozen scope, duplicate Celery deliveries must not repeat mutations, the 03:00 and 05:00 pipelines must recover after broker/worker interruption, HO must be the union of every campus report in the scheduled run, and Quiz planning must find every feasible exact allocation instead of depending on greedy ordering.

## 2. Scope and delivery stages

The implementation is split into four independently testable stages:

1. Core class-sync job safety and semantic idempotency.
2. Durable 03:00/05:00 scheduling and immutable report snapshots.
3. Progress-email reconciliation and scheduled queue cleanup.
4. Exact Quiz allocation and normalization edge cases.

Each stage must leave the application runnable and must include behavior tests that fail against the current snapshot before production code changes are made.

## 3. Terminology and business invariants

### 3.1 Campus and HO

- A campus report contains exactly one campus code from the scheduled parent's frozen campus set.
- **HO is not a campus. HO means the consolidated report for all campuses in the same scheduled parent, term, and branch.**
- The HO artifact must be produced only after every required campus artifact is complete.
- The HO artifact must be derived from the exact immutable campus snapshots belonging to that parent. It must not query the current academic tables again.
- For additive measures, the HO totals must equal the sum of campus totals from the same parent. For distinct measures such as unique students or teachers, HO must de-duplicate stable entity identifiers across campus snapshots rather than summing already-aggregated distinct counts.
- A campus failure, a missing campus snapshot, or a scope mismatch prevents HO publication and fails the parent.

### 3.2 Job completion

- `completed` means every mandatory target in the frozen request scope satisfied the business success policy.
- A partial account, enrollment, mapping, score, report, or email operation cannot be recorded as `completed`.
- Where partial results are useful to operators, they are preserved in `result_json`, but the terminal status remains `failed` unless a specific public `completed_with_errors` contract is introduced across API and UI. This change will use `failed` to avoid expanding the public status enum.

### 3.3 Idempotency and ownership

- A job may be reused only when its semantic fingerprint matches the full operation contract.
- Class ID alone, or class ID plus job type alone, is insufficient.
- Scheduled children belong to exactly one parent and cannot adopt a manual or foreign-parent job as their child.
- A conflicting active job may block dispatch, but it cannot satisfy another request.
- Every mutation intent receives a stable idempotency key before it is published to Celery or sent to an external service.

## 4. Core class-sync execution design

### 4.1 Semantic fingerprint

Create one canonical helper that normalizes and hashes:

- class ID;
- job type;
- force;
- limit;
- mode;
- `auto_map_course`;
- `sync_learning`;
- parent job ID and scheduled origin when present;
- frozen scope version/policy version.

Manual duplicate requests with the same fingerprint return the existing active job. A different active fingerprint for the same class returns an explicit conflict containing the blocking job ID. Bulk coordinators wait for the blocker to become terminal, then create their own correctly keyed child.

### 4.2 Atomic execution claim

`academic_class_sync_task` claims a job with one conditional database update equivalent to:

```sql
UPDATE academic_class_sync_jobs
SET status = 'running', started_at = COALESCE(started_at, now()), updated_at = now()
WHERE id = :job_id AND status = 'queued'
RETURNING id;
```

If no row is returned, the task exits without executing business logic. A duplicate delivery that sees `running` or a terminal status never repeats the operation. Recovery of abandoned `running` jobs belongs to the watchdog/reconciliation path, not to duplicate task delivery.

### 4.3 Retry policy

- Read-only `learning_sync` may use bounded automatic retry for classified transient errors.
- Account creation, enrollment, course mapping, and `full_cms_sync` are mutation workflows. After an ambiguous timeout they move to failed/reconcile-required metadata and are not blindly replayed.
- Reconciliation first reads remote Open edX state, calculates missing effects, and submits only missing mutations with the same idempotency intent.
- Retry counters, last failure class, and reconciliation outcome are stored in `result_json` for operator diagnosis.

### 4.4 Success policy

Account and enrollment services return explicit counts:

```text
target_count, eligible_count, succeeded_count, skipped_count, failed_count
```

They also return bounded failure details. A scheduled `full_cms_sync` succeeds only when `failed_count == 0`, every mandatory target is accounted for, and mapping/account/enrollment substeps all report success. `target_count == 0` is successful only when the frozen scope itself is genuinely empty; it is not successful when upstream mapping or discovery failed.

## 5. Durable scheduler design

### 5.1 Database changes

Add migration `0066_academic_pipeline_hardening` after `0065_academic_job_batch_recovery`.

It adds a nullable, unique, indexed `idempotency_key` to `academic_bulk_operation_jobs`. Existing rows remain valid. Scheduled parent keys use stable values:

```text
03:00: ap-daily:{run_date_vn}:{term_id}:{branch}
05:00: score-report-daily:{run_date_vn}:{term_id}:{branch}
```

Class-sync children continue using the existing unique `academic_class_sync_jobs.idempotency_key`, with keys containing parent ID, class ID, job type, and policy version.

### 5.2 Parent creation

Parent creation uses a database uniqueness constraint plus insert-or-load behavior. Advisory locks may reduce contention but are not the correctness boundary. Duplicate Beat deliveries load the same parent and safely nudge its continuation.

### 5.3 Durable continuation

Every state transition is committed before task publication. Failure to publish leaves a recoverable `dispatch_pending`/continuation marker in parent state. A periodic recovery scanner republishes non-terminal parents whose next continuation is due and not confirmed.

Publish exceptions are recorded; they are never swallowed. Coordinator retries use bounded attempts, exponential backoff, a per-target dispatch-attempt counter, and a maximum parent runtime. Persistent failure becomes terminal.

### 5.4 03:00 pipeline

The frozen sequence remains:

```text
AP sync
→ wait for AP terminal success
→ scheduled auto-map for the exact AP run/scope
→ full_cms_sync children
→ course mapping
→ Open edX account resolution/creation
→ student and teacher enrollment
```

The auto-map idempotency contract contains the AP sync run ID, term, branch, run date, and scope hash. A manual auto-map job never satisfies the scheduled continuation. Class discovery is paginated until exhaustion. A configured hard safety cap produces an explicit `scope_truncated` failure instead of silently completing.

### 5.5 05:00 pipeline

The parent freezes, before dispatch:

- exact class IDs;
- class-to-campus mapping;
- exact campus codes;
- term and branch;
- requested maximum student scope;
- run date and policy version.

Each `learning_sync` child belongs to that parent. A manual job is a blocker only. Report generation starts only after every frozen child is terminal and all are successful.

## 6. Immutable campus and HO report design

### 6.1 Snapshot creation

After all 05:00 score children succeed, one snapshot-building operation reads the required PostgreSQL data under one consistent database snapshot. It builds run-specific report payloads for:

- each campus in the frozen parent scope;
- one HO payload covering all frozen campuses.

Snapshot payloads include stable teacher, class, and student identifiers so HO can de-duplicate cross-campus entities correctly. They also include parent ID, term, branch, campus scope, source child IDs, source timestamps, row counts, and checksums.

Run-specific snapshots are stored separately from the mutable UI cache. The existing live cache may still be refreshed for page performance, but scheduled artifacts never depend on that mutable cache.

### 6.2 Artifact generation

Campus export jobs read only their matching immutable snapshot. The HO export job reads the campus snapshots for the same parent and validates:

- the snapshot campus set equals the parent's frozen campus set;
- every snapshot checksum is present;
- no campus appears twice;
- term, branch, parent, and policy version match;
- additive and distinct aggregation invariants hold.

Only then is the HO workbook written. `source_campus_report_job_ids` remains provenance metadata but is no longer the source of truth by itself.

### 6.3 Retention

Snapshots remain available for artifact reproducibility and audit. Cleanup is age-based and must not delete snapshots referenced by active or retained report jobs.

## 7. Progress-email design

- Persist a provider-facing idempotency key and a durable send intent before calling Mail Send.
- Persist provider session information immediately after the remote call returns.
- On timeout or worker loss, reconciliation queries provider state using the same idempotency key/session metadata before deciding whether to resend.
- The watchdog distinguishes `intent_created`, `provider_unknown`, `provider_created`, and terminal states.
- Recipient lists remain frozen and bounded; logs never include raw recipient addresses.

## 8. Queue routing

- Interactive/manual single-class work publishes to `sync-fast`.
- Scheduled/bulk children and all coordinator continuations publish to `sync-bulk`.
- New code publishes nothing to legacy `sync`.
- Legacy `sync` consumers may remain temporarily only to drain messages produced by the old release, after which they can be removed operationally.

## 9. Exact Quiz allocation

### 9.1 Difficulty × question type

Replace `_pair_targets()` greedy allocation with `feasible_type_difficulty_matrix()` or its flexible variant from `question_type_quota.py`. Strict native inventory must satisfy the exact row and column quotas. Legacy/flexible inventory uses the existing documented rebalance policy, but one question cannot be counted in multiple cells.

### 9.2 Release × quota pair

Replace `_allocate_final()` with an exact max-flow network:

```text
source
→ release nodes (release targets)
→ release/pair edges (inventory capacity)
→ pair nodes (pair targets)
→ sink
```

The planner fails only when maximum flow is smaller than the requested total. Allocation output remains deterministic through stable release and pair ordering.

## 10. Normalization and edge cases

- IDs are normalized only after checking `value is not None`; `None`, empty strings, and whitespace are discarded.
- Zero targets are valid only for explicitly empty scopes.
- Negative limits, quotas, retry counts, and capacities are rejected or clamped at the public boundary according to the existing API contract.
- Empty class/campus lists terminate without a continuation loop and record why the scope is empty.
- Single-item scopes follow the same state machine and aggregation rules as larger scopes.
- Coordinator loops have bounded attempts and maximum runtime.

## 11. Test strategy and acceptance criteria

Tests must exercise runtime behavior, not search source text.

### 11.1 Concurrency and idempotency

- Two task deliveries race for one queued class job; exactly one executes the service mutation.
- A delivery for a running job exits without mutation.
- Same semantic request reuses a job; different semantics returns a blocker conflict.
- A scheduled child never adopts a manual or foreign-parent job.
- Duplicate Beat delivery produces one parent per run date/term/branch.

### 11.2 Truthful terminal state

- One success and ninety-nine enrollment failures produce a failed child and parent.
- Mapping discovery failure with zero children produces failure, not completion.
- A missing learning result does not refresh unrelated snapshot timestamps.
- A persistent dispatch error terminates after the configured bound.

### 11.3 Reports

- Campus A contains only A; campus B contains only B.
- HO contains A and B and no campus outside the frozen set.
- HO additive totals equal campus additive totals.
- A teacher/student present in multiple campuses is counted once in HO distinct totals.
- Changing live academic rows after snapshot creation does not change campus or HO artifacts.
- A missing/failed campus snapshot prevents HO generation.

### 11.4 Quiz

- The known greedy counterexample resolves to Single/Medium plus Multi/Hard.
- The cross-release counterexample finds the feasible release/pair allocation.
- Truly infeasible matrices produce actionable validation errors.
- Zero, negative, empty, one-item, legacy-flexible, and deterministic-order cases are covered.

### 11.5 Email and queues

- Worker loss after provider acceptance does not create a second send session.
- Recovery completes an intent stranded before continuation publication.
- All new bulk paths publish to `sync-bulk`; no production path publishes to `sync`.

## 12. Deployment and rollback

1. Apply migration `0066` before deploying workers that write bulk idempotency keys.
2. Deploy backend/worker/beat code from the same image version.
3. Keep the legacy `sync` consumer only during the drain window.
4. Verify worker queue bindings and parent recovery scanner before enabling the daily schedules.
5. Run one controlled 03:00-equivalent scope and one 05:00-equivalent scope before full production scheduling.

Rollback may return application code to the prior version because the new bulk idempotency column is nullable and additive. Immutable report snapshots and reconciliation metadata remain harmless to the old application. The downgrade migration must not be run while new-version jobs are active.

## 13. Out of scope

- Redesigning the frontend job dashboard.
- Changing Open edX connector APIs unrelated to idempotency/reconciliation.
- Replacing Celery or Redis.
- Altering academic scoring policy or Excel presentation beyond the corrected campus/HO data source.
