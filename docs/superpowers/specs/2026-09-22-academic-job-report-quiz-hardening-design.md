# Academic Job, Daily Report, Email, and Quiz Hardening Design

## 1. Goal

Make the Dash CMS production workflows truthful and replay-safe: a completed job must mean the requested business operation completed for its entire frozen scope, duplicate Celery deliveries must not repeat mutations, the unified 01:00 Asia/Ho_Chi_Minh pipeline must recover after broker/worker interruption, score snapshots must expose only canonical assessment columns instead of course-outline noise, each branch-specific HO workbook must be the union of every campus report in that branch's scheduled run, and Quiz planning must find every feasible exact allocation instead of depending on greedy ordering.

## 2. Scope and delivery stages

The implementation is split into four independently testable stages:

1. Core class-sync job safety and semantic idempotency.
2. Durable unified 01:00 scheduling and branch-isolated immutable report snapshots.
3. Progress-email reconciliation and scheduled queue cleanup.
4. Exact Quiz allocation and normalization edge cases.

Each stage must leave the application runnable and must include behavior tests that fail against the current snapshot before production code changes are made.

## 3. Terminology and business invariants

### 3.1 Campus and HO

- A campus report contains exactly one campus code from the scheduled parent's frozen campus set.
- **HO is not a campus. HO means the consolidated report for all campuses in the same scheduled parent, term, and branch.** Poly and PTCD therefore produce separate `HO-Poly` and `HO-PTCD` artifacts.
- Every campus and HO row must match the scheduled branch. An explicit opposite-branch class or teacher is a hard validation failure, not a row to include or silently discard.
- A legacy teacher with a null branch inherits the class branch for validation. A teacher with an explicit branch must equal the class branch and scheduled branch.
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

- Manual read-only `learning_sync` may use bounded automatic retry for classified transient errors. Scheduled daily children report their first business failure to the stage coordinator; their business retries occur only at the end-of-stage barrier so all targets follow the same three-round policy.
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

### 5.1 Database changes and root identity

Add migration `0066_academic_pipeline_hardening` after `0065_academic_job_batch_recovery`.

It adds a nullable, unique, indexed `idempotency_key` to `academic_bulk_operation_jobs`. Existing rows remain valid. The single 01:00 run owns one durable root and stable branch/term scopes:

```text
root: academic-daily:v2:{run_date_vn}
provision scope: academic-daily:v2:{run_date_vn}:{term_id}:{branch}:provision
score/report scope: academic-daily:v2:{run_date_vn}:{term_id}:{branch}:score-report
```

Class-sync children continue using the existing unique `academic_class_sync_jobs.idempotency_key`, with keys containing parent ID, class ID, job type, and policy version.

### 5.2 Parent creation

Parent creation uses a database uniqueness constraint plus insert-or-load behavior. Advisory locks may reduce contention but are not the correctness boundary. Duplicate Beat deliveries load the same parent and safely nudge its continuation.

### 5.3 Durable continuation

Every state transition is committed before task publication. Failure to publish leaves a recoverable `dispatch_pending`/continuation marker in parent state. A periodic recovery scanner republishes non-terminal parents whose next continuation is due and not confirmed.

Publish exceptions are recorded; they are never swallowed. Coordinator retries use bounded attempts, exponential backoff, a per-target dispatch-attempt counter, and a maximum parent runtime. Persistent failure becomes terminal.

Application-stage retries are separate from Celery delivery retries. A stage always lets every job in its current attempt reach a terminal state before it schedules failed logical targets again. This prevents one early failure from consuming all retry capacity while the rest of the stage is still running.

### 5.4 Unified 01:00 pipeline

Celery Beat publishes exactly one root continuation at 01:00 Asia/Ho_Chi_Minh. The old 03:00 AP and 05:00 score/report publishers are disabled. The durable sequence is:

```text
AP sync for Poly and PTCD
→ wait for both branches' AP scopes to succeed
→ map missing subjects to CMS courses
→ create/resolve missing student Open edX accounts
→ enroll students who are not yet enrolled
→ update scores
→ wait for both branches' score scopes to succeed
→ export every campus workbook
→ wait for every campus artifact in each branch
→ build HO-Poly and HO-PTCD from their own campus snapshots
```

AP work for Poly and PTCD may run concurrently. Mutation, score, and report dispatch share one global concurrency budget of four jobs across both branches; separate branch coordinators must not each acquire a four-job window. Scope ordering is deterministic by branch and term so recovery resumes the same work without exceeding the global cap.

The auto-map idempotency contract contains the AP sync run ID, term, branch, run date, and scope hash. A manual auto-map job never satisfies the scheduled continuation. Class discovery is paginated until exhaustion. A configured hard safety cap produces an explicit `scope_truncated` failure instead of silently completing.

### 5.5 Cross-branch barrier and frozen score/report scope

Before score dispatch, each branch/term scope freezes:

- exact class IDs;
- class-to-campus mapping;
- exact campus codes;
- term and branch;
- requested maximum student scope;
- run date and policy version.

Each `learning_sync` child belongs to its scheduled scope. A manual job is a blocker only. Campus report generation starts only after every frozen score child for both Poly and PTCD is terminal and successful. After the stage retry budget is exhausted, a missing active branch, truncated scope, or mandatory failure is fail-closed: the root records the failed stage, branch, scope, and child IDs; it publishes no new campus or HO artifact. Previously successful artifacts remain downloadable and are not presented as results of the failed run.

### 5.6 End-of-stage retry barrier

The root treats the daily flow as six ordered stages:

1. AP synchronization for Poly and PTCD;
2. missing subject-to-course mapping;
3. missing student account creation and enrollment;
4. score update;
5. campus snapshot and workbook export;
6. branch-specific HO aggregation and workbook export.

For each stage, attempt zero runs every frozen logical target once. After all jobs in that attempt are terminal, the coordinator freezes the failed target set and runs only those targets again. It performs at most three retry rounds (`1`, `2`, and `3`), so one logical target can execute at most four times including its initial attempt. Each retry round must finish before the next round is created. Successful targets are never repeated.

The four-job global concurrency limit applies to initial work and every retry round across Poly and PTCD combined. The parent durably records the stage, retry round, frozen failed target IDs, child attempt IDs, failure classifications, and next continuation before publishing retry jobs. Recovery loads this state and resumes the same round instead of consuming another retry.

Read-only and deterministic export targets may be re-executed directly. Before retrying a mutation target, the coordinator reconciles the current database and Open edX state using the original mutation intent key, then submits only missing effects. An ambiguous timeout is never treated as proof that the remote mutation failed. Every retry attempt has a unique job identity for audit, while all attempts share the same logical target and external idempotency intent.

A stage advances only when all frozen targets have succeeded. If any target is still failed after retry round three, the root becomes terminal `failed`, records the exhausted targets and their last errors, and does not dispatch the next stage. A validation or scope-integrity failure may be reconsidered in each end-of-stage retry round, but it never bypasses validation and never becomes successful merely because the retry budget is exhausted.

### 5.7 Canonical assessment-component boundary

Open edX may return both actual assessment grades and structural course nodes through duplicated containers such as `component_scores`, `grade.components`, `items`, or `subsections`. The raw connector response remains unchanged in the learning snapshot for diagnostics, but student-list, teacher-report, and Excel payloads pass through one canonical assessment selector before exposing dynamic columns.

The canonical display contract is:

- a numbered quiz is identified by a human-facing label such as `Quiz 7`, `Learning Check 7`, or `LC 7`; alternatively it may use a positive `quiz_number` only when the connector also supplies explicit `assessment_type=quiz`;
- `quiz_number` by itself is untrusted because the connector's course-outline fallback may assign sequential positions to any graded subsection; a row named `Demo` or `Phần 1` remains excluded even when it carries a positive `quiz_number` or `category=quiz`;
- all rows for the same quiz number collapse to one `quiz:{number}` column, preferring a real scored row over a planned course-outline shell;
- a Final test is represented by at most one `final_test` column when the row has explicit `assessment_type=final_test` or a normalized human-facing `Final test` label;
- structural or demonstration rows such as `Demo`, `Demo 1`, `Demo bài 1`, and repeated `Phần 1` through `Phần 4` are not assessment columns, even when their usage keys differ or Open edX stores incidental problem scores beneath them;
- Assignment remains represented by the existing Assignment/defense contract and is not duplicated as a dynamic grade column;
- an empty canonical assessment set is valid and produces no dynamic assessment columns rather than guessing from storage keys or generic list position.

This filtering does not alter the stored total grade, progress, raw snapshot, or exam-eligibility rules. The same canonical identity and preference rules must be used by class student responses, class/teacher component summaries, and workbook column discovery so the UI and exports cannot disagree.

## 6. Immutable campus and HO report design

### 6.1 Snapshot creation

After all score children for both branches succeed, including their end-of-stage retry rounds, snapshot-building reads the required PostgreSQL data under a consistent database snapshot. It builds run-specific report payloads for:

- each campus in the frozen parent scope;
- one branch-specific HO payload covering all frozen campuses for that branch.

Snapshot payloads include stable teacher, class, and student identifiers so HO can de-duplicate cross-campus entities correctly. They also include parent ID, term, branch, campus scope, source child IDs, source timestamps, row counts, and checksums.

Snapshot creation validates `class.branch` and the effective teacher branch (`teacher.branch` when set, otherwise `class.branch`) against the scheduled branch. This validation is symmetric: Poly snapshots reject PTCD data and PTCD snapshots reject Poly data. Campus ownership must also belong to the scheduled branch. Any mismatch fails the snapshot and blocks publication.

Run-specific snapshots are stored separately from the mutable UI cache. The existing live cache may still be refreshed for page performance, but scheduled artifacts never depend on that mutable cache.

### 6.2 Artifact generation

Campus export jobs read only their matching immutable snapshot. The HO export job reads the campus snapshots for the same parent and validates:

- the snapshot campus set equals the parent's frozen campus set;
- every snapshot checksum is present;
- no campus appears twice;
- term, branch, parent, and policy version match;
- every class, effective teacher branch, and campus source matches the artifact branch;
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
- Duplicate Beat delivery produces one root per Vietnam run date and one stable branch/term scope per stage.
- The unified dispatcher never has more than four active mutation, score, or report jobs across Poly and PTCD combined.
- The legacy 03:00 and 05:00 schedules do not publish new pipeline roots.
- A failed target is retried only after every job in the current stage attempt is terminal.
- Each retry round contains only the still-failed logical targets, never successful targets, and the global active-job count remains at most four.
- Duplicate continuation delivery resumes the persisted retry round without creating a fourth retry or duplicate mutation intent.

### 11.2 Truthful terminal state

- One success and ninety-nine enrollment failures produce a failed child and parent.
- Mapping discovery failure with zero children produces failure, not completion.
- A missing learning result does not refresh unrelated snapshot timestamps.
- A persistent dispatch error terminates after the configured bound.
- A target that succeeds in retry round one allows the stage to advance after all other targets succeed.
- A target still failing after retry rounds one, two, and three fails the root and prevents the next stage from dispatching.
- An ambiguous mutation timeout is reconciled before retry and only the missing remote effect is submitted.

### 11.3 Reports

- Campus A contains only A; campus B contains only B.
- HO contains A and B and no campus outside the frozen set.
- `HO-Poly` rejects every PTCD class, teacher, and campus row; `HO-PTCD` rejects every Poly class, teacher, and campus row.
- Campus workbooks enforce the same two-way branch isolation as HO.
- An explicit teacher branch that differs from its class branch fails snapshot creation; a null legacy teacher branch inherits the class branch.
- No campus or HO report is published when either branch has an incomplete mandatory score scope.
- HO additive totals equal campus additive totals.
- A teacher/student present in multiple campuses is counted once in HO distinct totals.
- Changing live academic rows after snapshot creation does not change campus or HO artifacts.
- A missing/failed campus snapshot prevents HO generation.
- Student lists, teacher reports, and Excel exports expose the same canonical assessment columns.
- A payload containing `Quiz 1`, repeated `Demo`, repeated `Phần 1`, and one `Final test` produces exactly `Quiz 1` and `Final test` dynamic columns.
- Duplicate quiz rows with different usage keys collapse by quiz number and prefer real scores over planned shells; a structural row with a position-derived `quiz_number` stays excluded, and raw snapshot JSON remains intact for diagnosis.

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
4. Verify worker queue bindings, the global four-job lease/window, persisted retry-round recovery, and the parent recovery scanner before enabling the daily schedule.
5. Disable the old 03:00 and 05:00 Beat entries, enable the single 01:00 Asia/Ho_Chi_Minh entry, and verify only one root is created per Vietnam run date.
6. Run one controlled end-to-end 01:00-equivalent execution containing both Poly and PTCD before full production scheduling; verify branch-specific campus and HO artifacts.

Rollback may return application code to the prior version because the new bulk idempotency column is nullable and additive. Immutable report snapshots and reconciliation metadata remain harmless to the old application. The downgrade migration must not be run while new-version jobs are active.

## 13. Out of scope

- Redesigning the frontend job dashboard.
- Changing Open edX connector APIs unrelated to idempotency/reconciliation.
- Replacing Celery or Redis.
- Altering academic scoring policy or Excel presentation beyond the corrected campus/HO data source, branch isolation, and removal of non-assessment dynamic grade columns.
