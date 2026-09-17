# Academic Sync RBAC, Windowing, and Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make assigned teachers able to run only the two class-scoped CMS actions, freeze bulk job scope at enqueue time, bound score refreshes to ten active classes, prevent false queued-orphan failures, and remove the analytics 500/performance defects.

**Architecture:** Keep authorization in two layers: a dedicated business permission admits the class-scoped routes, then `assert_can_access_class` enforces the AP assignment. Bulk operations persist immutable class/subject snapshots and coordinators dispatch at most ten child jobs at a time. Analytics summary endpoints aggregate in SQL and only load bounded detail lists.

**Tech Stack:** FastAPI, SQLAlchemy, Celery, pytest, Next.js/TypeScript.

**Spec:** User-approved bounded design in the 2026-09-17 conversation; no separate architectural spec is required.

## Global Constraints

- Teachers may run the two actions only for AP-assigned classes.
- Full CMS sync must enqueue with `sync_learning=false`.
- Score refresh must run `learning_sync` only.
- Admin and campus-owner behavior remains unchanged.
- Every behavior change follows RED-GREEN verification.

---

### Task 1: Assigned-teacher class sync authorization

**Files:**
- Modify: `backend/app/services/business_rbac.py`
- Modify: `backend/app/api/routes/academic.py`
- Modify: `frontend/app/student-management/classes/[classId]/page.tsx`
- Test: `backend/app/tests/test_assigned_teacher_class_sync_permission.py`

- [ ] Write tests proving `TEACHER_ASSIGNED` receives `academic.sync_assigned_class`, the route dependency accepts it, and `assert_can_access_class` still rejects another class.
- [ ] Run the focused tests and confirm the missing permission fails.
- [ ] Add the permission to the RBAC catalog/role and use it in the class-scoped sync dependency.
- [ ] Update the frontend visibility predicate and send Full CMS with `syncLearning: false`.
- [ ] Run focused backend and frontend checks.

### Task 2: Immutable auto-map snapshot and audit semantics

**Files:**
- Modify: `backend/app/services/academic_service.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/api/routes/academic.py`
- Test: `backend/app/tests/test_academic_auto_map_snapshot.py`

- [ ] Write a failing worker/service test proving a class remains in scope after its learning status changes after enqueue.
- [ ] Run it and confirm the worker's second filter causes the failure.
- [ ] Add a snapshot-based auto-map path using only approved subject/class IDs and remove `learning_status` from worker selection.
- [ ] Record enqueue audit as `success` and retain `job_status=queued` in metadata.
- [ ] Run focused tests.

### Task 3: Ten-class score refresh coordinator and queued lease

**Files:**
- Modify: `backend/app/services/academic/student_management_runtime.py`
- Modify: `backend/app/services/academic/job_runtime.py`
- Modify: `backend/app/api/routes/academic.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/app/tests/test_academic_latest_score_window.py`
- Test: `backend/app/tests/test_academic_auto_map_batch_coordinator.py`
- Test: `backend/app/tests/test_academic_job_runtime.py`

- [ ] Write failing tests proving only ten children are enqueued, completed slots release the next classes, and class-sync queued jobs use a broker-aligned lease.
- [ ] Run them and confirm current eager fan-out/900-second behavior fails.
- [ ] Reuse `plan_batch_dispatch` in score refresh and let its watchdog dispatch subsequent windows.
- [ ] Set the window default to ten and use the effective class-sync queued lease consistently.
- [ ] Run focused coordinator/watchdog tests.

### Task 4: Analytics correctness and bounded aggregation

**Files:**
- Modify: `backend/app/services/learning_analytics/analytics_core_service.py`
- Modify: `backend/app/services/learning_analytics/results.py`
- Test: `backend/app/tests/test_learning_analytics_regressions.py`

- [ ] Write failing tests calling both affected instance methods and checking dashboard totals/top lists over more rows than the response limit.
- [ ] Run them and confirm the staticmethod TypeError.
- [ ] Remove the invalid decorators and replace dashboard full-row Python aggregation with SQL aggregate queries plus bounded detail queries.
- [ ] Run analytics tests.

### Task 5: Full verification and handoff

**Files:**
- Review all changed files.

- [ ] Run Ruff/compile and focused backend tests.
- [ ] Run frontend lint, typecheck, and production build.
- [ ] Run the broad backend suite and separate pre-existing failures from regressions.
- [ ] Review the final diff against every user requirement.
- [ ] Commit, push the feature branch, and report the exact commit/verification status.
