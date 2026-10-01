# Analytics Retention and Daily Pipeline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove production analytics statement timeouts and make the 01:00 academic pipeline operate on a safe CMS-only frozen scope with truthful mapping failures.

**Architecture:** Add two production-safe PostgreSQL indexes, split raw-event identity access into indexed branches, and rewrite cleanup as bounded candidate/proof/delete batches. Align daily scope discovery and auto-map result contracts so business contractions are retried normally while scope expansion remains a permission error.

**Tech Stack:** Python 3, SQLAlchemy, PostgreSQL, Alembic, Celery, pytest, SQLite test fixtures.

**Spec:** `docs/superpowers/specs/2026-09-30-analytics-retention-daily-pipeline-recovery-design.md`

## Global Constraints

- Keep `db_statement_timeout_ms=5000`; do not increase the global timeout.
- Keep raw-event retention at exactly 3 days.
- Build production indexes concurrently and idempotently.
- Delete only old video/quiz events proven represented by durable materializations.
- Use a cleanup batch size of 5,000, at most 10 batches per run, hourly schedule, and a transaction-local timeout of 60,000 ms.
- Preserve Loki as raw source of truth and durable video/quiz materializations as historical state.
- Preserve Poly/PTCD branch/campus isolation and reject any mapped class outside the frozen scope.
- Exclude explicit non-CMS delivery, including Udemy; retain legacy no-delivery/NULL-delivery CMS behavior.

## Review Focus

- One raw event matches both username and user-id branches: process it once in stable order.
- A class has an explicit inactive or Udemy delivery next to a legacy class: only valid CMS semantics enter the frozen scope.
- The oldest cleanup candidates are unmaterialized while later old rows are safe: stop boundedly and report blockage without deleting unsafe rows.
- The mapper returns failed classes but no mapped classes: persist subject detail and fail normally, never as permission drift.
- The mapper returns one unknown class ID: reject the whole result before dispatching any downstream work.

---

### Task 1: Concurrent analytics indexes and bounded retention configuration

**Files:**
- Create: `backend/alembic/versions/0069_analytics_tracking_query_indexes.py`
- Create: `backend/app/tests/test_analytics_tracking_query_indexes.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/tests/test_v25_9_25_analytics_retention.py`

**Interfaces:**
- Produces: PostgreSQL indexes `ix_analytics_events_course_user_id_time` and `ix_analytics_tracking_events_created_id`.
- Produces: settings `analytics_raw_event_cleanup_batch_size=5000`, `analytics_raw_event_cleanup_interval_seconds=3600`, and `analytics_raw_event_cleanup_statement_timeout_ms=60000`.
- Consumes: Alembic head `0068_analytics_loki_ingest`.

- [ ] **Step 1: Write failing migration and settings tests**

Add behavior tests that execute `upgrade()`/`downgrade()` through a captured Alembic operation facade for PostgreSQL and assert concurrent create/drop inside an autocommit block. Extend retention-default assertions with the exact bounded values.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest -q app/tests/test_analytics_tracking_query_indexes.py app/tests/test_v25_9_25_analytics_retention.py`

Expected: FAIL because revision `0069` and the new timeout setting do not exist and current batch/interval values differ.

- [ ] **Step 3: Add migration and settings**

Implement `upgrade() -> None` and `downgrade() -> None` following the existing `0062` autocommit/concurrent pattern, with non-PostgreSQL fallback through normal Alembic index operations. Change only the cleanup defaults named in this task.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest -q app/tests/test_analytics_tracking_query_indexes.py app/tests/test_v25_9_25_analytics_retention.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `fix: add analytics retention query indexes`

### Task 2: Indexed identity event loading

**Files:**
- Modify: `backend/app/services/learning_analytics/analytics_core_service.py`
- Create: `backend/app/tests/test_analytics_identity_event_loading.py`
- Modify: `backend/app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py`

**Interfaces:**
- Produces: `_tracking_events_for_identity(base_query, identity) -> list[AnalyticsTrackingEvent]`, returning primary-key de-duplicated events sorted by `(event_time, loki_ts_ns, id)`.
- Consumes: Task 1's `(course_id, user_id, event_time)` index for the user-id branch and the existing username composite index.
- Produces: video, quiz, and event-count paths that no longer emit the username/user-id `OR` predicate.

- [ ] **Step 1: Write failing identity-loader tests**

Use a real SQLite event table and SQL capture to prove separate username/user-id SELECT statements, de-duplication of dual matches, stable null-safe ordering, empty-identity short circuit, and class-scoped counts.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest -q app/tests/test_analytics_identity_event_loading.py app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py`

Expected: FAIL because the loader does not exist and callers still use `_apply_tracking_identity_filter`.

- [ ] **Step 3: Implement and integrate the loader**

Replace `_apply_tracking_identity_filter` usage in video, quiz, and class event counts with two branch queries. Keep unscoped username behavior and existing canonical identity rules unchanged. Use the loader result for `source_event_exists` so the class path does not perform a second unscoped query.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest -q app/tests/test_analytics_identity_event_loading.py app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py app/tests/test_v25_9_25_analytics_retention.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `fix: split analytics identity event queries`

### Task 3: Indexed two-phase retention cleanup

**Files:**
- Modify: `backend/app/services/learning_analytics/analytics_core_service.py`
- Modify: `backend/app/tests/test_v25_9_25_analytics_retention.py`

**Interfaces:**
- Consumes: Task 1's `(created_at, id)` index and 60,000 ms cleanup timeout setting.
- Produces: `cleanup_tracking_events() -> dict[str, Any]` with candidate, proven, deleted, batch, remaining-old, and blocked-unmaterialized counters.
- Preserves: advisory lock and active-recalculation skip behavior.

- [ ] **Step 1: Write failing cleanup behavior tests**

Add PostgreSQL SQL-capture tests for transaction-local timeout, candidate-first bounded scan, separate identity proof branches without join `OR`, and `blocked_unmaterialized`. Add SQLite/service-level tests for unchanged non-PostgreSQL and active-job skips.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest -q app/tests/test_v25_9_25_analytics_retention.py`

Expected: FAIL because current cleanup uses one large delete CTE, no local timeout, and no blocked result.

- [ ] **Step 3: Implement bounded candidate/proof/delete batches**

Select old video/quiz IDs by `(created_at, id)`, prove exact per-event coverage, and delete only proven IDs. The final review hardening stores coverage receipts in revision `0070`; video and quiz recalculation write them in the same transaction as materialization, and cleanup joins candidates by receipt primary key. Commit per batch, stop on lock/contention or an unmaterialized oldest window, and return bounded audit counters.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest -q app/tests/test_v25_9_25_analytics_retention.py app/tests/test_analytics_identity_event_loading.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `fix: bound analytics retention cleanup`

### Task 4: CMS-only daily scope and truthful auto-map results

**Files:**
- Modify: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/services/academic_service.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/tests/test_academic_daily_pipeline_ap_mapping.py`
- Modify: `backend/app/tests/test_academic_auto_map_snapshot.py`
- Modify: `backend/app/tests/test_academic_auto_map_batch_coordinator.py`

**Interfaces:**
- Produces: frozen daily scopes whose `class_ids`, `class_to_campus`, subject IDs, and hash use `cms_delivery_predicate()` semantics.
- Produces: auto-map result keys `approved_class_ids`, `mapped_class_ids`, `failed_class_ids`, and per-subject `class_ids`.
- Consumes: worker subset validation; any union of mapped/failed classes outside approved IDs raises `PermissionError`, while a strict subset remains a business result.
- Preserves: existing stage retry controller and fail-closed stage barrier.

- [ ] **Step 1: Write failing scope and result-contract tests**

Add real SQLite tests for CMS/legacy/Udemy scope discovery and post-AP refresh. Add service tests for mapped and failed class partitioning. Add worker/coordinator tests that a strict subset yields structured mapping failure/retry while an outside ID is rejected before dispatch.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest -q app/tests/test_academic_daily_pipeline_ap_mapping.py app/tests/test_academic_auto_map_snapshot.py app/tests/test_academic_auto_map_batch_coordinator.py`

Expected: FAIL because scope discovery includes explicit non-CMS classes and the worker requires exact set equality.

- [ ] **Step 3: Implement CMS scope and auto-map contract**

Join subject delivery using the existing delivery dimensions and apply active `cms_delivery_predicate()` semantics in both discovery and refresh. An inactive explicit row is excluded and is not treated as a missing legacy delivery. Partition approved classes by subject result, include bounded failure detail, validate only scope expansion as permission drift, persist prepared state, and let `map_only` fail normally when `subject_failed > 0`. Recovered `dispatching` jobs derive their approved scope before phase branching.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest -q app/tests/test_academic_daily_pipeline_ap_mapping.py app/tests/test_academic_auto_map_snapshot.py app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_academic_scheduled_parent_recovery.py app/tests/test_academic_job_retry_api_contract.py`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `fix: align daily CMS mapping scope`

### Task 5: Whole-branch regression and operator verification contract

**Files:**
- Modify as required by failures in Tasks 1-4; no unrelated refactors.

**Interfaces:**
- Consumes: all prior task interfaces.
- Produces: a green backend suite, valid Alembic graph, and reviewed deployment-ready diff.

- [ ] **Step 1: Run focused combined regression**

Run: `cd backend && pytest -q app/tests/test_analytics_tracking_query_indexes.py app/tests/test_analytics_identity_event_loading.py app/tests/test_v25_9_25_analytics_retention.py app/tests/test_academic_daily_pipeline_ap_mapping.py app/tests/test_academic_auto_map_snapshot.py app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_academic_scheduled_parent_recovery.py app/tests/test_academic_job_retry_api_contract.py`

Expected: PASS.

- [ ] **Step 2: Validate Alembic graph and Python syntax**

Run: `cd backend && alembic heads && python -m compileall -q app alembic/versions`

Expected: exactly one head, `0070_analytics_materialized_event_receipts`, and exit code 0.

- [ ] **Step 3: Run the complete backend suite**

Run: `cd backend && pytest -q`

Expected: PASS with zero failures; any pre-existing failure is named explicitly and investigated before completion.

- [ ] **Step 4: Review the whole branch and fix Critical/Important findings through RED→GREEN**

Create the executing-plans review package from the branch merge base, request one fresh-context review, and apply the single permitted fix pass.

- [ ] **Step 5: Commit verified integration changes**

Commit message if a final fix pass is required: `fix: address analytics pipeline review findings`
