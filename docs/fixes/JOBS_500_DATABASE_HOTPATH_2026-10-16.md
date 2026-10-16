# Hotfix /jobs 500 — PostgreSQL read hot paths (16/10/2026)

## Verified incident and bounds

Production logs at 10:42 + read-only EXPLAIN on 16/10 show
psycopg.errors.QueryCanceled (statement_timeout = 10s) for:

- GET /api/academic/sync/class-jobs?status=failed&limit=100:
  WHERE status='failed' ORDER BY created_at DESC LIMIT 100.
  ~215752 estimated live job rows; plan used created_at index and postfiltered status.
- GET /api/analytics/ops/status:
  unbounded SELECT COUNT(*) FROM analytics_tracking_events.
  ~14447732 estimated live tracking rows; parallel index-only count scanned
  millions of entries. Original source also repeated production/rollout reports.

No evidence of Cloudflare, frontend drawer, pod OOM, or auth causing these two 500s.
Open URLs later returning 200 is compatible with transient statement timeouts.

## Changes

- Alembic 0074: (status, created_at) composite index with PostgreSQL
  CREATE INDEX CONCURRENTLY; migration statement timeout scoped to 120s,
  lock wait bounded to 5s; retry handles INVALID existing index.
  Health readiness requires 0074; migration must run before backend rollout.
- List class jobs: one batched access decision, preserving assignment /
  campus-branch / subject union and pre-existing newest-N candidate window.
  Reconciliation behavior and job history remain unchanged.
- Analytics ops: use planner relation estimate only for display and expose
  tracking_event_count_is_estimate; exact threshold check uses a LIMIT-bounded
  count for production readiness, independent of relation estimate.
  Reuse data-quality / rollout / monitoring results in one ops request.
- Rollout: keep effective course mapping rules, replace 3 per-class aggregate
  reads with three bounded GROUP BY queries.

Do not raise global DB_STATEMENT_TIMEOUT_MS to mask slow plans. Do not delete,
reset, truncate or backfill tracking events for this fix. CMS-FPT not affected.

## Acceptance on UAT

1. Alembic upgrade through 0074, check index validity (pg_index.indisvalid),
   GET /health/ready. Confirm no concurrent table write outage.
2. Explain on UAT: failed class job query should favor status_created index;
   evaluate EXPLAIN (ANALYZE, BUFFERS) with a safe UAT workload.
3. GET /api/academic/sync/class-jobs?status=failed&limit=100:
   200 with same schema, newest order, scoped Poly/PTCD class visibility,
   no cross-branch leakage and no changed job state beyond existing reconcile.
4. GET /api/analytics/ops/status: 200; count carries estimate marker,
   readiness threshold accurate even with stale PostgreSQL statistics.
   Compare counters to real data using an offline/background verification,
   not by making web requests count millions of rows.
5. Run targeted pytest tests plus auth/academic and readiness regression.
   Measure 30+ equivalent requests at target concurrency; record p50/p95/p99,
   database query count, PostgreSQL locks and CPU/IO before/after.
6. Verify no new errors in application logs and monitor for 10-30 minutes
   before production rollout. Smoke and rollback plan are mandatory.

## Rollback / pending risks

Migration downgrade concurrently drops only the added index. Downgrade health
expectation and application schema in lockstep; never roll back schema blindly
while new application binaries are serving. If migration waits too long, stop
the rollout and review locks before retry; do not enlarge cluster-wide timeout.

PG estimated tracking count is intentionally not exact and can lag ANALYZE;
minimum readiness condition remains exact by bounded count. Very high configured
min_events still increases bounded count cost; monitor thresholds.

**Status:** source patch on fix branch; testing, UAT, image digest and production
rollout not verified when this document was authored. Baseline source
4e2d9e41bbad5460d971d08d527e53cc14108924.
