# Video Relative Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Video-first explainable relative ranking with median/MAD and Isolation Forest comparison.
**Architecture:** Extend existing materialization/evidence/worker/API/card, no new service or migration. Persist speed-aware measurements separately from wall-time rules; pool configured courses with canonical roster deduplication.
**Tech Stack:** Python, SQLAlchemy, NumPy, scikit-learn, Next.js, pytest, Playwright, GitHub CI.
**Spec:** docs/superpowers/specs/2026-10-19-video-relative-ranking-design.md

## Global Constraints

- Minimum 30 distinct learners; 30–49 low confidence; max reference 5,000.
- Video first; quiz disabled independently; global off hides stored scores.
- No grade/rule changes, no verdict labels, no fitting in GET.
- Bounded source/roster reads, current outline, version and scope validation.
- Supported video speed up to 4x; no guessed historical playback data.

## Review Focus

- Mixed legacy/new progress: incomplete history must never supply trusted full-history features.
- Seek/play duplicates and batch boundaries: no fake coverage or double-counted media time.
- Configured cross-course learner identity: one learner per cohort and only target persistence.
- MAD ties/constant columns: no fake ordering, zero division or misleading comparison agreement.
- Global/family switch changed during a job: no reads/writes or visible stale ranking after disabling.

### Task 1: Measurements and ranking engines

**Files:** add `video_playback.py`; modify `ml_features.py`, `ml_anomaly.py`, materialization in `analytics_core_service.py`; add `test_video_relative_ranking.py`, update existing feature/scorer tests.
**Interfaces:** `measure_playback(events, previous=None, historical_data=False)->dict`; `score_cohorts(rows, min_students=30, max_students=5000, cancelled=None, seed=42)->dict`; `MLFeatureRow.metadata` carries informational rates/counts. Existing result keys remain stable per family/cohort/learner.

- [ ] Write tests for 30 people, missing playback, same content at 1x/2x, seek exclusion, incremental state and legacy history; assert injected learners occupy top five in both engines and all seed pairs overlap >=0.8.
- [ ] Run `pytest -q app/tests/test_video_relative_ranking.py`; expect failures for missing v2 behavior.
- [ ] Implement measurements and MAD/IF scores, version v2; retain compatible deferred quiz implementation.
- [ ] Run new and existing ML feature/scorer tests plus video materialization regressions; expect all green.
- [ ] Commit task with verification evidence.

### Task 2: Pooling, controls and presentation

**Files:** `ml_workflow.py`, `ml_presentation.py`, `core/config.py`, env examples, frontend types/card; workflow/access tests and frontend/browser tests.
**Interfaces:** consume Task 1 evidence; `ml_enabled(class_id, family='video')`; serialize relative-score evidence and confidence only, allowlist comparison/deviation fields.

- [ ] Add failing tests for configured cross-course pool reaching 30 distinct people, duplicate memberships, family/global off before database reads, stale data and low confidence presentation; add rendered UI copy test.
- [ ] Run tests and observe intended failures.
- [ ] Implement batch pooling and independent switches, preserve rule evidence and transaction/cutoff guards; card shows ranking and MAD features, comparison on disagreement.
- [ ] Run workflow/access and rendered UI tests, lint/typecheck/build; expect green.
- [ ] Commit task with verification evidence.

### Task 3: Evaluation, CI and integration

**Files:** `scripts/evaluate-learning-ml.py`, replay tests, `scripts/ci-backend-tests.sh`, runbook/CURRENT_STATE/index/catalog.
**Interfaces:** same runtime feature/scorer functions, video-only report by default; explicit quiz evaluation remains an offline diagnostic option.

- [ ] Add failing tests for skip-group reports and source-preserving video-only replay; implement report and benchmarks.
- [ ] Run focused/backend CI selection and whole suite; compare historical failure names against committed baseline; test 1,000/5,000 rows in fresh processes.
- [ ] Run frontend/browser checks and independent whole-branch review; fix material findings with reproductions.
- [ ] Update docs and catalog, publish PR using GitHub API if direct Git transport unavailable; exact-head CI must pass.
- [ ] Merge to `feat/import-quiz-cms-old-su26` after fresh branch/head/CI check; verify merged tree and report tests/skipped cohorts/deployment state.
