# AP/daily/video verification — 12/11/2026

Baseline source9164170; Python3.12 local SQLite, fake Celery dispatch boundaries;
Node24.22.1, frontend Next14.2.35. No production cluster/credentials/data used.

- `pytest -q`: **312 failed,1464 passed,16 skipped (103.11s)**. Exact failure node
  set equals AP baseline312 failed/1418passed/16skipped. No added/resolved failures.
  All baseline node names: [09/11 report](AP_LEARNING_RESULTS_2026-11-09.md).
- CI selected source suite:563passed; release subset6passed/1deselected. Local
  integration2failed/14skipped because no PostgreSQL migration table and missing
  REDIS_URL, same environment baseline (not a passing integration claim).
- AP and existing workspace/access regression subset:62passed (includes32 AP tests).
- Video scoped10modules:132passed, including paused resume-gap and old coverage-marker
  regressions observed failing before fix; active explicit seeks and same-position
  resumes still valid. Full backend covers the integrated source.
- Daily adjacent contracts:136passed, including21 new failure-isolation tests.
  Mixed mapping end-to-end fake-dispatch scenario retains good subject/classes,
  exports healthy campuses/branch HO, blocks dependent classes; final root failed
  with original cause and partial artifacts. Completed-empty mapping and snapshot
  metadata rejected; entirely failed scope parents do not claim partial success.
- Frontend `node --test tests/*.test.cjs`:46passed (13 reason/display tests).
  `npm run lint`, `npm run typecheck`, `npm run build`:pass.
- `ruff check app --select E9,F63,F7,F82`, compileall, git diff check:pass.
- Independent review found two material issues (empty completed snapshots and
  unobserved paused gaps), plus false partial-success parent labeling. Regression
  RED→GREEN verifies all fixes; no deferred review findings.

No PostgreSQL concurrency/query-plan, live broker delivery, K8s rollout or AP
consumer smoke test performed. Existing daily business-failed root remains terminal;
version-old analytics need worker recomputation/replay when logs still exist.
