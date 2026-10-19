# Video ranking v2 verification — 19/10/2026

Baseline dbd0c62; source branch feat/video-learning-ranking-20261019. This is source/test evidence, not runtime deployment. [Current runbook](../LEARNING_ANALYTICS_ML_ROLLOUT.md) defines controls and rollout.

## Observed checks

- Baseline before edits: 67 focused ML tests passed.
- Feature/scorer RED: 16 failed, 1 passed. Materializer integration RED: 2 failed,17 passed. Task 1 scoped GREEN:67 passed.
- Pool/controls RED:3 failures; API RED:5; rendered UI RED:2; pool-change-during-fit RED:1. Task 2 GREEN:98 backend and28 frontend tests, lint/typecheck/build passed.
- Replay/performance RED:5 failures; updated video-only behavior GREEN:9 passed.
- Independent reviewer: gpt-6-astra, dbd0c62..3559db9, no edits. Three Important findings: timestamp-only dedup; orphan initial stop accepted as complete; further source reads after disable. Replay outline mixing initially Minor, regraded Important because it can incorrectly qualify a 30-person cohort.
- One fix pass: regressions for four findings, same-timestamp materialization without Loki nanoseconds, resumed video without initial history, and normalized disabled-quiz aliases. Reproductions failed before fixes. Playback28 checks, workflow20, replay11 passed during fix; final combined focused suite116 passed.
- Full tracked-source suite after fixes:1350 passed,16 skipped,312 failed in42.70s. Compare classname::name sets against LEARNING_ML_TEST_BASELINE_2026-10-16.txt; historical failures remain, do not describe full suite as green. Untracked browser artifacts/node_modules excluded from this comparison.
- Frontend:28 node unit/rendered checks and35 Playwright desktop/mobile smoke passed; lint, typecheck, production build passed. New rendered checks run in frontend CI; new backend acceptance checks run through ci-backend-tests.sh.
- Local integration cannot verify PostgreSQL/Redis: two known missing-environment failures (migration smoke and Redis TTL),14 skipped. Exact-head remote CI must supply PostgreSQL16/Redis7, run migration/down-up, concurrency, images and Compose before merge.

## Measured data and limits

Retained audit:3 classes,83 unique roster learners,0 video v2 eligible,0 scored groups. Reasons:83 insufficient measured videos,38 missing playback measurements,1 invalid measurement; reasons overlap. Quiz ML disabled for5195 normalized learner/unit groups. Official export SHA256 unchanged:eb8c6daa427dd1a8f3f79109c0ed3677579b78d5ded25cc713844efe447bb21c. Export hash does not prove production recalculation ran.

Synthetic benchmark (fresh Python3.12.14 process, Linux x86_64,9 logical CPUs,one model thread):1000 rows0.9252s/110.84MiB incremental peak RSS;5000 rows1.1019s/123.51MiB. Both satisfy provisional <10s/<256MiB. Includes first import, excludes DB I/O/concurrent app worker/full production RSS.

Seeds0,1,7,42,99: five injected near-100%-completion/very-low-coverage people occupy both engines' top five; all seed pairs overlap100%. Seek/passive features remain within ordinary ranges. No production accuracy or universal stability claim; teacher-labelled samples and representative cohorts remain future work.

## Decisions and remaining verification

User waived further approval and authorized CI-gated merge. Execution used a manual plan ledger because cloud skill helper scripts were unavailable locally. Original checkout metadata was missing; all1751 Git blobs and signed dbd0c62 commit were reconstructed/verified, root tree0b65fff02efa9e1e66f0d0a3365823ba652bcf66; no source changes preceded recovery.

Replay outline consistency was treated as a release-blocking correctness issue and fixed. Production telemetry completeness, compatible plugin deployment, labelled accuracy and full workflow performance are unverified; global mode/pilots remain off/empty. PostgreSQL locking and exact-head CI are mandatory merge checks, not inferred from unit tests. Source/context/catalog must be published together; use PR status for final CI/merge SHA.
