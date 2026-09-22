# Academic Job, Report, Email, and Quiz Hardening Implementation Plan

> Approved on 2026-09-22. Execute continuously with TDD and verification after every task.

**Goal:** Make class jobs, scheduled pipelines, reports, progress email, queue routing, and quiz allocation truthful, durable, replay-safe, and exact.

**Design:** See `docs/superpowers/specs/2026-09-22-academic-job-report-quiz-hardening-design.md`.

**Delivery rule:** Write a behavior test that fails for the intended reason, implement the smallest coherent change, run focused tests, then run the relevant regression set. Persist completed milestones as fast-forward commits on `feat/import-quiz-cms-old-su26`.

## Task 1: Semantic class-sync identity and conflict behavior

- Add `backend/app/services/academic/job_identity.py`.
- Add `backend/app/tests/test_academic_job_semantic_identity.py`.
- Canonicalize the complete operation contract and hash stable JSON under `class-sync:v2:`.
- Reuse only the same active fingerprint.
- Treat a different active fingerprint for the class as an explicit blocker.
- Ensure scheduled children never adopt manual or foreign-parent jobs.

## Task 2: Atomic queued-to-running execution claim

- Add `backend/app/services/academic/job_claim.py`.
- Add concurrency and duplicate-delivery tests.
- Claim with one conditional `queued -> running` update.
- Exit without service mutation when the claim returns no row.
- Leave abandoned-running recovery to watchdog/reconciliation.

## Task 3: Truthful success and mutation retry boundaries

- Add behavior tests for partial failures, empty discovery failures, and ambiguous mutation timeouts.
- Return explicit target/eligible/succeeded/skipped/failed counts.
- Fail mandatory workflows when any mandatory target is unaccounted for.
- Permit bounded automatic retries only for classified read-only transient failures.
- Record reconcile-required metadata for ambiguous mutation outcomes.

## Task 4: Migration 0066 and immutable report-snapshot schema

- Add `backend/alembic/versions/0066_academic_pipeline_hardening.py`.
- Add nullable unique indexed `idempotency_key` to bulk jobs.
- Add run-specific snapshot metadata keyed by parent, scope type, and campus.
- Store payloads in object storage with checksum/provenance metadata.
- Update model and migration-head tests.

## Task 5: Idempotent parents and durable continuation recovery

- Create/load scheduled parents by stable key under the database uniqueness boundary.
- Commit state before publishing continuation tasks.
- Persist dispatch-pending state, attempt counts, due time, and last error.
- Add a bounded recovery scanner for non-terminal parents.
- Never swallow publish exceptions.

## Task 6: Freeze complete 03:00 and 05:00 scopes

- Freeze exact term, branch, class IDs, class-to-campus mapping, campuses, run date, requested maximum scope, and policy version.
- Paginate discovery until exhaustion.
- Turn safety-cap truncation into explicit failure.
- Require scheduled auto-map and children to match the exact parent contract.
- Treat foreign active jobs as blockers only.

## Task 7: Immutable one-campus snapshots

- Build all campus payloads from one consistent database snapshot after all score children succeed.
- Ensure each campus payload contains exactly that campus.
- Include stable teacher, class, and student identifiers plus checksums and source child IDs.
- Make scheduled exports read only the immutable snapshot.
- Keep mutable UI caches outside the artifact source of truth.

## Task 8: True HO aggregate

- Validate that campus snapshots exactly match the parent's frozen campus set.
- Fail on missing, failed, duplicate, or scope-mismatched campus snapshots.
- Build HO only from campus snapshot payloads.
- Sum additive measures and de-duplicate distinct teacher/student entities by stable identifiers.
- Never query live academic tables during HO generation.

## Task 9: Route all bulk work to sync-bulk

- Route manual single-class work to `sync-fast`.
- Route scheduled/bulk children and coordinator continuations to `sync-bulk`.
- Add routing tests proving new production paths do not publish to legacy `sync`.

## Task 10: Durable progress-email intent and reconciliation

- Persist provider idempotency intent before Mail Send.
- Persist provider session metadata immediately after the call.
- Reconcile `intent_created`, `provider_unknown`, and `provider_created` states.
- Prevent resend after worker loss following provider acceptance.
- Preserve frozen recipients and redact addresses from logs.

## Task 11: Exact difficulty-by-question-type allocation

- Replace greedy `_pair_targets()` with the existing exact feasibility matrix helper.
- Cover strict native and documented flexible legacy behavior.
- Add the known greedy counterexample and truly infeasible cases.
- Preserve deterministic output ordering.

## Task 12: Exact release-by-pair allocation and ID normalization

- Replace greedy `_allocate_final()` with deterministic max flow over releases and quota pairs.
- Fail only when maximum flow is below requested total.
- Normalize IDs only after checking for `None`; discard empty/whitespace values.
- Cover zero, negative, empty, one-item, and cross-release counterexamples.

## Task 13: Full verification and release

- Run focused backend tests for every changed subsystem.
- Run migration-head and migration upgrade checks.
- Run `python -m compileall backend/app`.
- Run backend regression suite and frontend type/lint/build checks available in the repository.
- Review the final diff against the approved design.
- Re-read the remote branch ref, create fast-forward commit(s), and update without force.
- Report exact commands, results, commit SHA, and any environment-only limitations.
