# AP Learning Results Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose scoped read-only analytics to AP without recalculation on page load.

**Architecture:** A dedicated API-key dependency authenticates explicit branch/campus scopes. A small query service resolves AP identities, joins the current roster to durable snapshots, and returns versioned whitelisted DTOs.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy; existing PostgreSQL tables.

**Spec:** docs/superpowers/specs/2026-11-09-ap-learning-results.md

## Global Constraints

- Exact student_code case; branch/campus pairs; AP identifiers distinct from Dash UUIDs.
- GETs only; no tracking scan, queue, Redis dependency, or external network call.
- Maximum page size 200; deterministic roster ordering; explicit missing/stale state.
- Preserve existing internal APIs and RBAC.

## Review Focus

- Missing/invalid credentials and malformed config must fail closed.
- Duplicate AP identities and case-normalized snapshot usernames must not pick an arbitrary row.
- Cross-class/course/inactive/outsider snapshots must never appear.
- Missing and stale results must not look like normal learning or zero grades.
- Page size must bound hydrated students/snapshots; summary must cover the whole roster.

### Task 1: Scoped authentication and results API

**Files:** Create `backend/app/core/ap_analytics_auth.py`, `backend/app/services/ap_learning_results.py`, `backend/app/schemas/ap_learning_results.py`, `backend/app/api/routes/ap_learning_results.py`, `backend/app/tests/test_ap_learning_results.py`; modify config and router.

**Interfaces:** `get_ap_analytics_client` returns an immutable scoped client; `APLearningResultsService.class_results` / `student_result` return stable DTO dictionaries for the routes.

- [x] Write tests for credential failures, paired scopes, identity resolution, missing/stale/zero values, privacy, bounded pagination and GET-only OpenAPI.
- [x] Run scoped pytest; confirm missing implementation failure.
- [x] Implement config, auth, query service, DTOs and GET routes.
- [x] Run scoped tests and existing analytics access/performance regression tests; fix only introduced failures.

### Task 2: Integration handoff and verification

**Files:** Create `docs/AP_LEARNING_RESULTS_API.md`; update `docs/INDEX.md`, `docs/CURRENT_STATE.md`, `CODE_INDEX.md`; catalog after source commit.

- [x] Document headers, secret generation/rotation, scope config, request/response/status contracts and deployment checks.
- [x] Run lint, full backend tests and compare failing node IDs with the recorded baseline.
- [x] Obtain independent whole-branch review, address material findings with regressions.
- [x] Commit/publish source using Conventional Commits, then rebuild/publish catalog from remote source SHA and verify clean index.

Execution record: AP tests RED for missing module →18pass; review regressions RED→25pass; related total55pass. Full suite retains exact312 baseline failures (1418pass/16skip). Current task branch reused existing clean checkout; user authorized implementation and business-branch publication. No deployment or external account changes.
