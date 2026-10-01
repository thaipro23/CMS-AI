# Analytics Retention and Daily Pipeline Recovery Design

**Date:** 2026-09-30
**Status:** Proposed
**Target branch:** `feat/import-quiz-cms-old-su26`

## 1. Problem statement

Two production workflows are failing for separate but related scale and scope-contract reasons.

1. `learning_analytics_recalculate` is cancelled by PostgreSQL's global five-second `statement_timeout`. The raw event table is about 8.9 GB with roughly 3.1 million live rows. Recalculation filters a course by `(username IN (...) OR user_id IN (...))`, while production has no `user_id` lookup index. The query also materializes full ORM rows, including JSON payloads.
2. Raw-event retention is configured for three days, but every cleanup attempt is cancelled. Cleanup orders candidates by `created_at`, for which production has no index, and evaluates a large `OR`/`EXISTS`/`LEFT JOIN` expression before limiting the batch.
3. The scheduled academic pipeline freezes every active class in a branch, but the Course CMS mapper returns only classes whose subjects mapped successfully. The worker treats any legitimate contraction as a security-scope mismatch. A single non-CMS or unmappable subject therefore causes the mapping branch to retry four times and the parent pipeline to finish as `course_mapping exhausted`.

The model declarations contain some `index=True` flags, but those declarations do not retrofit indexes into an existing production database. The repair therefore requires an explicit Alembic migration as well as query and workflow changes.

## 2. Goals and success criteria

### Analytics

- A class recalculation completes without raising `QueryCanceled` under the normal five-second global timeout for indexed lookup batches.
- Recalculation keeps the existing identity rules: Open edX `user_id` is preferred, Open edX username is the fallback, and ambiguous mappings remain fail-closed.
- Raw video and quiz events older than three days are deleted only after a matching durable materialization exists.
- Cleanup makes bounded, observable progress without changing the global database timeout.
- Historical video/quiz analytics remain available from the durable materialized tables; Loki remains the raw source of truth.

### Daily academic pipeline

- The Course CMS stage freezes only the classes governed by CMS delivery semantics.
- A mapper result that is a subset of its frozen scope is not classified as a permission violation.
- A mapper result containing any class outside its frozen scope is still rejected.
- Actual subject mapping failures are recorded with subject identifiers and messages, retried by the existing stage retry controller, and reported as the real terminal cause if retries are exhausted.
- Poly/PTCD, branch, campus, and requester access isolation remain fail-closed.

## 3. Non-goals and safety constraints

- Do not increase `db_statement_timeout_ms` globally.
- Do not run `VACUUM FULL`, rewrite the 8.9 GB table, or perform a blocking production maintenance operation as part of deployment.
- Do not delete raw events merely because they are old. They must first be proven represented by the corresponding video or quiz materialization.
- Do not broaden a scheduled job beyond its durable frozen scope.
- Do not include explicitly Udemy-delivered classes in CMS mapping, provisioning, score, or report stages.
- Do not change the global scheduled pipeline concurrency policy; existing logical-target retry and global active-job limits remain authoritative.

## 4. Database index design

Add Alembic revision `0069_analytics_tracking_query_indexes` after `0068_analytics_loki_ingest`.

The migration adds only the two indexes missing from the production access paths:

| Index | Columns | Purpose |
|---|---|---|
| `ix_analytics_events_course_user_id_time` | `(course_id, user_id, event_time)` | Supports the Open edX `user_id` identity branch during video and quiz recalculation. |
| `ix_analytics_tracking_events_created_id` | `(created_at, id)` | Supports deterministic retention candidate scanning and the remaining-old-row probe. |

The existing `(course_id, username, event_time)` index continues to serve the username identity branch. A separate simple `user_id` index is intentionally omitted because the composite index matches the production query prefix and avoids redundant write/storage cost. `event_type` remains a residual filter; ingestion stores the relevant analytics families and the identity/course predicates should reduce the candidate set before payload loading.

On PostgreSQL, both indexes are built with `CREATE INDEX CONCURRENTLY IF NOT EXISTS` inside Alembic's autocommit block. Downgrade uses `DROP INDEX CONCURRENTLY IF EXISTS`. Non-PostgreSQL development/test databases use normal Alembic index operations. This avoids a long write lock on ingestion while preserving repeatable local migrations.

Review hardening adds revision `0070_analytics_materialized_event_receipts`. It creates a narrow receipt table keyed by raw event ID. A receipt stores the event family and the exact canonical AP identity used by successful recalculation. The foreign key cascades when the retained raw row is deleted, so the proof table remains bounded to raw rows awaiting cleanup.

## 5. Analytics recalculation design

Replace the single identity predicate containing SQL `OR` with two indexed branches:

1. Query events by `course_id` and `username IN (...)` using the existing course/username/time index.
2. Query events by `course_id` and `user_id IN (...)` using the new course/user-id/time index.
3. Merge the results by event primary key so an event matching both branches is processed once.
4. Sort the merged set deterministically by `(event_time, loki_ts_ns, id)` before applying existing video or quiz state logic.

The query keeps the current event-family predicate and any video-specific predicate. It fetches only events matched by the class's immutable identity map; no unscoped course scan is allowed. Payload fields required by the existing video and quiz processors remain available, but unrelated rows are never hydrated.

If both raw identity sets are empty, the helper returns an empty result without querying the event table. Identity canonicalization remains unchanged: a unique `user_id` mapping wins, then a unique username mapping; ambiguous identities are not silently attributed.

The helper is shared by video, quiz, and any class-event existence check so the expensive `OR` is not reintroduced through a secondary path.

## 6. Retention cleanup design

Cleanup becomes a two-phase bounded operation.

### 6.1 Candidate scan

- Select at most `analytics_raw_event_cleanup_batch_size` event IDs older than the three-day cutoff.
- Scan in `(created_at, id)` order through the new index.
- Limit the scan to video and quiz event families.
- Lock selected rows with `FOR UPDATE SKIP LOCKED` while holding the existing analytics ingest advisory lock.

### 6.2 Materialization proof and delete

- Video and quiz recalculation write a per-event receipt in the same transaction as their durable materialization.
- Each receipt records the canonical identity chosen by recalculation, so `user_id` precedence and ambiguous-identity fail-closed behavior cannot diverge during cleanup.
- Video receipts are written only after the cumulative watermark covers the event. Quiz receipts are written only for normalized events that contribute to a materialized attempt.
- Cleanup proves coverage by primary-key joining candidates to receipts; the presence of an unrelated progress or attempt row is never accepted as proof.
- Delete only the selected IDs that have proof. Commit after every batch to release locks promptly.
- If old candidates exist but none can be proven materialized, stop the run and return a `blocked_unmaterialized` result instead of spinning or reporting misleading success.

Production defaults change to:

| Setting | Value | Rationale |
|---|---:|---|
| `analytics_raw_event_retention_days` | `3` | Required staging window. |
| `analytics_raw_event_cleanup_batch_size` | `5000` | Keeps each statement bounded under production load. |
| `analytics_raw_event_cleanup_max_batches_per_run` | `10` | Caps one run at 50,000 deletions. |
| `analytics_raw_event_cleanup_interval_seconds` | `3600` | Allows the existing backlog to drain without a single large transaction. |
| `analytics_raw_event_cleanup_statement_timeout_ms` | `60000` | Transaction-local ceiling for the maintenance statement only. |

Cleanup sets the timeout with transaction-local PostgreSQL configuration before each batch. It never changes the session default or global database setting. Cleanup still skips when recalculation jobs are queued/running and still uses the single analytics queue, preventing maintenance from competing with active class recalculation.

The result/audit payload records candidate rows scanned, rows proven safe, rows deleted, batches completed, old rows remaining, and blocked-unmaterialized count. Counts are concise; full generated SQL and bound identity lists are not stored in job errors.

PostgreSQL autovacuum is allowed to reclaim and reuse dead space after deletion. Physical file shrinkage is not a deployment success criterion.

## 7. CMS-only scheduled scope design

Daily scope discovery and the post-AP refresh apply the shared `cms_delivery_predicate()` semantics, but only to active delivery rows:

- no delivery row: CMS for legacy compatibility;
- `learning_platform IS NULL`: CMS for legacy compatibility;
- `learning_platform = 'cms'`: CMS;
- any explicit non-CMS platform, including Udemy: excluded.
- any inactive explicit delivery, regardless of platform: excluded rather than reinterpreted as an absent legacy delivery.

The predicate is applied while selecting active classes for each frozen branch/campus scope. The refreshed class list, class-to-campus map, subject list, and `scope_hash` therefore describe the same CMS-only contract used by the mapping worker. Campus validation continues to reject classes that fall outside the frozen branch campuses.

Later provisioning, enrollment, score, and teacher-report stages consume the frozen CMS class IDs; they must not rediscover or append classes from an unfiltered term query.

## 8. Auto-map result contract and retry behavior

`auto_map_subject_courses_for_snapshot()` returns a structured result with:

- `approved_class_ids`: the immutable input class scope;
- `mapped_class_ids`: approved classes whose subjects are mapped and can continue;
- `failed_class_ids`: approved classes blocked by a failed/unavailable subject mapping;
- `subject_results`: per-subject status, code, message, and affected class IDs;
- aggregate mapped/already-mapped/failed counts.

The worker applies two separate checks:

1. **Security check:** `mapped_class_ids` and `failed_class_ids` must both be subsets of `approved_class_ids`; any outside ID raises `PermissionError`.
2. **Business outcome:** a strict subset is valid preparation, not scope tampering. For `map_only`, any `subject_failed > 0` produces a normal failed job with the structured mapping result persisted before the exception/status transition.

The daily stage controller retries only failed logical branch targets at the end of the mapping round, using the existing maximum of the initial attempt plus three retry rounds. Successful branch targets are reused and are not re-run. If retries are exhausted, the parent error names the affected branch target and summarizes the first bounded set of failed subject codes; it does not replace the cause with `frozen parent scope`.

The pipeline remains fail-closed at the stage barrier: downstream CMS provisioning starts only after every mapping target in the frozen CMS scope succeeds. This prevents partially mapped classes from receiving inconsistent accounts/enrollments while allowing independent branch targets to finish and be reused.

## 9. Error reporting and observability

Job error strings must be bounded and operator-oriented.

- Analytics timeout failures report the operation, course/class target, batch/identity sizes, and PostgreSQL error class; they do not embed thousands of SQL bind placeholders.
- Mapping failures report branch/scope key, failed subject count, and a bounded list of subject codes/messages.
- Cleanup audits expose progress and blocked counts so an operator can distinguish "nothing old", "not materialized", "active recalculation", and a real database failure.

Existing job IDs, progress, attempt number, logical target key, and parent linkage remain intact for UI drill-down and audit history.

## 10. Test strategy

Implementation follows test-driven development. Tests are added or changed before production code.

### Migration and query tests

- Alembic head advances from `0068` to `0069` and declares both expected indexes.
- PostgreSQL migration SQL uses concurrent create/drop and an autocommit block.
- Username and user-id event branches return a stable de-duplicated sequence.
- Generated identity lookup paths do not contain a username/user-id `OR`.
- Empty identities issue no event-table query.

### Retention tests

- Events newer than three days are retained.
- Old events without durable materialization are retained and reported blocked.
- Old video and quiz events with exact materialization receipts are deleted.
- Receipts preserve the recalculation identity decision and are not created for events beyond a video watermark or skipped quiz input.
- Batch size, max batches, advisory lock, active-recalculation skip, and transaction-local timeout are honored.
- Non-PostgreSQL cleanup remains a no-op.

### Pipeline tests

- Explicit Udemy classes are excluded; CMS and legacy/unset delivery classes remain included.
- Post-AP refreshed scope/hash contains only CMS classes.
- A mapped subset of the approved scope is accepted as a business result.
- Any returned class outside the approved scope is rejected.
- Failed subject details are persisted and drive normal retry/exhaustion reporting.
- A successful branch is not retried when another branch fails.
- Branch/campus and Poly/PTCD access boundaries remain enforced.

Run the focused suites first, then the complete backend test suite and Alembic head/upgrade checks against PostgreSQL-compatible SQL generation.

## 11. Deployment and verification

1. Back up the production database according to the normal release procedure and confirm sufficient free index storage.
2. Deploy the migration. Observe both concurrent index builds in `pg_stat_progress_create_index`; do not cancel them merely because they run longer than an application request.
3. Confirm both indexes are valid in `pg_index` before rolling application workers.
4. Roll the backend, analytics worker, bulk worker, and beat from one identical image digest.
5. Trigger one representative failed class recalculation and verify completion time, row count, and absence of `QueryCanceled`.
6. Run one cleanup task, verify bounded deletion/audit counters, then allow hourly cleanup to drain the backlog.
7. Trigger the scheduled pipeline for one Poly and one PTCD scope and confirm CMS-only scope, explicit mapping errors, and reuse of successful targets.
8. Monitor database I/O, lock waits, job queue depth, cleanup deletion rate, and old-row count. Roll back application behavior if needed; leave valid indexes in place unless they independently cause a demonstrated regression.

No manual bulk delete or `VACUUM FULL` is performed before these safeguards are deployed.
