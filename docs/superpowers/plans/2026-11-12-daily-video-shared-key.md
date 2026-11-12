# Shared AP Key and Isolated Daily/Video Corrections Implementation Plan

> **For agentic workers:** Use scoped parallel investigation/implementation, then one integrated review.

**Goal:** One AP key; failed dependency scopes do not block unrelated daily work;
repeated measured seek/low-watch patterns receive review and readable reasons.

**Architecture:** Retain current FastAPI/Celery snapshot architecture, preserve
frozen job scopes and durable attempt history, version only the behavior rules.

**Tech Stack:** Python/SQLAlchemy/FastAPI, Celery, Next.js/TypeScript.

**Spec:** docs/superpowers/specs/2026-11-12-daily-video-shared-key-design.md

## Global Constraints

Exact student_code case and branch/campus scope; no arbitrary course selection,
raw answers in API, GET data writes, quiz reset, Redis/PVC changes, production job edits.

## Review Focus

- One key with multiple explicit scope pairs must not permit a scope cross product.
- Mapping partial results and retries must not lose healthy subjects/classes.
- Unknown/malformed result partitions fail only their own dependency scope closed.
- Missing timing or resumed video near the end must not become proof of low watch.
- Old snapshot warnings must agree between AP summary and Dash detail; no GET mutation.

## Task 1 — Shared key and presentation

- [x] Reproduce key-only rejection and missing shared-config contract.
- [x] Implement single-key auth with explicit scopes and safe legacy migration.
- [x] Reproduce missing friendly labels and test all requested codes, neutral
  reasons, timing/zero/missing displays; wire both views to shared resolver.
- [x] Test API scalar version projection and stale summary, preserve privacy.

## Task 2 — Dependency isolation

- [x] Reproduce global fail-all mapping behavior and retry/report variants.
- [x] Persist per-target failures and exclusions; advance independent targets.
- [x] Verify adjacent daily tests, retain retry/idempotency/terminal guards.

## Task 3 — Video verdict

- [x] Reproduce measured seek patterns scoring35 but NORMAL/NO_ACTION.
- [x] Review repeated corroborated cases, protect incomplete timing and resume.
- [x] Version stale results without mutation; scoped backend regressions pass.

## Task 4 — Delivery

- [x] Complete independent review and full tests, compare exact baseline failures.
- [x] Update context/runbook/index; commit source and publish business branch.
- [x] Build catalog from actual remote source SHA and verify clean final tree.

Execution evidence: AP32 pass; video132 scoped pass; daily136 scoped pass (21 isolation regressions); full312 baseline failures unchanged/1464pass/16skip; frontend46pass+lint+typecheck+build. Review reproductions and fixes recorded in runbook. No deferred findings or changes to production. Source/catalog publication tracked by resulting commits.
