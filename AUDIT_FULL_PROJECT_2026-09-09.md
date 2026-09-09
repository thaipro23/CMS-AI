# DASH CMS — FULL PROJECT AUDIT 2026-09-09

Scope: `thaipro23/CMS-AI`, branch `feat/import-quiz-cms-old-su26`.

This audit distinguishes **source-verified** findings from items that still require **production runtime verification**. It covers Training Operations performance, database access paths, frontend UX/UI on multiple device sizes, OWASP-oriented application security, Kubernetes hardening, logging/observability, background workers, and maintainability.

## 1. Executive status

### Implemented in this change

1. **Training Operations database scope indexes**
   - New Alembic head: `0062_v25_9_16_7_2_64_40`.
   - `academic_classes`: term-first expression/partial index matching `Học kỳ -> Hệ -> Cơ sở`, followed by subject/class keys.
   - `academic_subject_deliveries`: term + normalized branch + learning platform + subject/block index.
   - PostgreSQL creates both indexes concurrently inside Alembic autocommit; existing AP identity indexes remain unchanged.

2. **Migration/runtime guards updated**
   - Backend readiness expects Alembic head `0062_v25_9_16_7_2_64_40`.
   - Backend readiness, UAT/data-health guards and CI integration/release checks are synchronized to the new head. The older Claude review-pack head constant remains a follow-up cleanup item.

3. **Project-wide audit recorded**
   - Responsive UX/UI, OWASP-oriented security, performance/query hotspots, logging/observability, Celery reliability, K8s hardening, DB-pool sizing and maintainability were reviewed from source.
   - Findings below are recommendations/runtime-verification items unless explicitly marked implemented.

## 2. Training Operations performance analysis

### Why the new index order matters

The operator workflow scopes data in this order:

`Học kỳ -> Hệ -> Cơ sở -> Môn/Lớp`

The old class scope index is branch-first and was designed primarily for AP identity lookup. A branch-first index cannot efficiently serve term-only reads and is suboptimal for the initial Training Operations scope. The new index starts with `term_id` and then uses the same normalized branch/campus expressions present in the SQLAlchemy filters, so PostgreSQL can use the complete leading key sequence rather than only the semester prefix.

### Important remaining hotspot

`backend/app/services/academic_service.py::list_teacher_subjects()` still performs a full `.all()` of all matching class rows **inside the selected semester/scope**, builds subject buckets in Python, calculates learning/mapping state, and only then applies some status filtering/pagination.

The new term-first index improves the dominant scope access path, but this method is still the next P1 scaling target because it materializes matching rows before Python-side pagination. A phase-2 redesign should page subject IDs in SQL and aggregate class/student/teacher counts with grouped subqueries before enriching only the current page. Status filters that depend on learning snapshots need an equivalent database-side aggregate or a cached summary table to preserve semantics.

Static query-hotspot scan currently reports:

- `20` blockers
- `76` warnings
- `283` informational hits

The highest-priority blockers include Training Operations teacher report, Udemy progress, `list_teacher_subjects`, learning analytics results, and several Question Bank operations. Static findings require per-query review because some `.all()` calls are legitimately bounded by a parent object, but `list_teacher_subjects()` is a confirmed scale concern.

## 3. UX/UI and multi-device review

### Source-verified strengths

- 42 active application pages are covered by the layout integrity audit.
- 200+ responsive `@media (max-width...)` rules exist across the frontend.
- The root viewport is mobile-aware.
- Shared `EnterpriseDataTable` preserves all columns and uses horizontal scrolling instead of silently deleting data on narrow screens.
- The synchronized bottom horizontal rail is now sticky on long Student/Analytics tables.
- The Student Management and Analytics top-level page stacks have route-scoped protection against the legacy grid overlap bug.
- Layout integrity: `15/15 READY`.
- Full frontend design contract: `30/30 READY`.

### P2 UX/accessibility debt

- CSS is highly fragmented: 29 CSS files plus a very large `frontend/app/globals.css`; multiple late hotfix layers can override each other. This already caused the page-stack overlap and sticky-scroll regression. Consolidating route-specific hotfixes into component-owned/final contract layers should be a planned refactor.
- There are many 8–10 px text declarations. These should be reviewed for meaningful labels/status text and raised to an accessible floor where they are not purely decorative metadata.
- `outline: none` exists in several CSS locations. Each must keep an explicit `:focus-visible` replacement; do not remove outlines globally.
- Very wide operational tables are acceptable on tablet/mobile only while their scroll container and sticky rail remain intact. Browser regression should include 360, 768, 1024, 1366 and 1920 px widths.
- Several historical release-specific frontend tests no longer describe the current intentional UX. Current contract scripts are the canonical UI gates.

## 4. OWASP / application security review

### Source-verified controls

- Production/UAT config fails closed for unsafe debug/demo settings.
- Credentialed CORS requires an explicit allowlist; wildcard production CORS is rejected.
- Mutating cookie-auth requests have Origin/Referer protection.
- Production auth uses secure HttpOnly cookies; production frontend does not persist bearer tokens.
- Session JTI revocation, one-time bridge tickets and exchange rate limits are present.
- Security headers include nosniff, frame denial, referrer policy, permissions policy and HSTS in production.
- Metrics can require a strong token and fail closed in production.
- AP TLS mode defaults to strict.
- Production security source gate: `15/15 READY`.
- The only `dangerouslySetInnerHTML` occurrence found in frontend is the hardcoded shell bootstrap, not a user-supplied HTML field.

### Remaining security items requiring follow-up/runtime evidence

- Some user-file validation routes intentionally echo `ValueError` reasons. Parser libraries must never put secrets, internal paths or upstream payloads into those ValueErrors. Keep unexpected exceptions behind `public_http_exception`.
- Dependency CVE status was **not** verified in this offline workspace. CI should run an advisory/SBOM step for Python and npm dependencies rather than relying on `npm ci --no-audit` alone.
- Frontend/reverse-proxy CSP and edge HSTS need runtime/header verification; backend API headers alone do not prove the browser document response is fully hardened.
- `--forwarded-allow-ips=*` is acceptable only when the backend can be reached solely through trusted cluster proxies. Restrict it if the backend service is exposed to any untrusted network path.
- NetworkPolicy is absent from the base manifests. Add only after mapping Redis/PostgreSQL/MinIO/Open edX/ingress egress requirements.

## 5. Logging and observability

### Current state

- Gunicorn access/error logs go to stdout/stderr, appropriate for Kubernetes/Loki collection.
- API responses expose `X-Request-ID` and `X-Process-Time-Ms`.
- Unhandled exceptions use the common error envelope and server-side logging.
- Health/readiness endpoints include DB/storage/security/performance/maintainability/query-hotspot checks.

### P1/P2 follow-up

- Add bounded slow-request/5xx structured logging keyed by request ID, method, normalized path, status and duration; do not log query strings/bodies/authorization headers.
- Add Prometheus request-duration histogram/counters by normalized route, not raw path IDs, if not already provided by infrastructure instrumentation.
- Add explicit Celery task duration/failure counters by task name/queue.
- Define Loki retention, node/container log rotation and alert thresholds at infrastructure level.
- Alert on migration mismatch, performance-readiness failure, repeated 5xx, worker queue age, Redis unavailable, DB pool exhaustion and Open edX upstream failures.

## 6. Database and connection-pool review

Current defaults:

- `DB_POOL_SIZE=10`
- `DB_MAX_OVERFLOW=20`
- `DB_POOL_TIMEOUT=30`
- `DB_POOL_RECYCLE=1800`
- `DB_STATEMENT_TIMEOUT_MS=5000`

The API deployment has multiple Gunicorn workers and there are multiple Celery deployments. SQLAlchemy pools are process-local, so theoretical PostgreSQL connection demand can multiply quickly. Production must compare actual `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, pod counts and worker concurrency against PostgreSQL `max_connections`. Do not raise pool sizes to solve latency without this calculation.

Recommended runtime check:

```sql
SHOW max_connections;
SELECT application_name, state, count(*)
FROM pg_stat_activity
GROUP BY application_name, state
ORDER BY count(*) DESC;
```

## 7. Celery/background worker review

Positive source contracts:

- late acknowledgement enabled
- reject on worker loss
- prefetch multiplier 1
- max tasks per child
- max memory per child
- soft/hard time limits
- separate interactive/sync, heavy generation/export and analytics queues.

Runtime follow-up:

- monitor queue age, not only queue length
- compare concurrency to DB pool limits and CPU/memory limits
- verify worker OOM/restart trends
- verify Redis persistence/availability appropriate for durable workflow expectations.

## 8. Kubernetes availability review

### Current source posture

- Base manifests already use non-root/immutable container controls and resource requests/limits.
- Readiness/liveness probes exist for backend/frontend.
- No Kubernetes manifest change is included in this index/audit commit.

### Remaining platform improvements

- No HPA in base manifests.
- No PodDisruptionBudget in base manifests.
- No NetworkPolicy in base manifests.
- No startupProbe in base manifests.
- Image pull policy remains `IfNotPresent`; production should always deploy a unique immutable tag or digest. Reusing a mutable tag can reproduce the stale-two-replica bundle problem observed previously.

HPA/PDB/NetworkPolicy should be introduced only with production metrics/topology, not guessed from source.

## 9. Maintainability review

Large modules increase regression cost:

- `backend/app/services/academic_service.py` ~4k lines
- `backend/app/api/routes/academic.py` ~3.5k lines
- `backend/app/worker.py` ~3k lines
- Question Bank services/routes are also multi-thousand-line modules
- `frontend/lib/api.ts` ~5k lines
- `frontend/types/index.ts` ~4k lines
- `frontend/app/globals.css` ~8k+ lines.

Recommended phased refactor, without changing behavior:

1. split AcademicService by student/teacher/course-mapping/list-query responsibilities;
2. extract Training Operations SQL read models from mutation services;
3. split frontend API client by domain;
4. consolidate final CSS contracts and retire superseded hotfix rules;
5. retain static contract tests at component/domain boundaries rather than release-number-specific exact-string tests.

## 10. Verification performed in this workspace

Passed:

- Python compile for changed backend/migration files.
- Targeted migration/AP/UI regression tests passed during development.
- Alembic head resolves to `0062_v25_9_16_7_2_64_40` under a local SQLite config.
- Student/Analytics overlap + sticky-scroll frontend regressions: `3/3`.
- Frontend layout integrity: `15/15 READY`.
- Full frontend design contract: `30/30 READY`.
- Production security source gate: `15/15 READY`.

Not verified in this local workspace:

- full frontend `npm build/typecheck` because `frontend/node_modules` is absent;
- full PostgreSQL integration suite because local Python environment lacks `psycopg`;
- actual production `EXPLAIN ANALYZE`, index size/hit ratio, DB pool use, Loki retention, reverse-proxy headers, HPA/cluster metrics, dependency CVEs.

## 11. Production rollout order

1. Build backend image from this source using a **new immutable tag**.
2. Run migration Job first and wait for `0062_v25_9_16_7_2_64_40`.
3. Verify both indexes exist and are valid.
4. Roll backend/workers.
5. Build/roll frontend only if frontend files in this change are included in the release.
6. Verify `/api/health/ready`; verify the two index names directly in PostgreSQL using the SQL below.
7. Measure Training Operations API latency before/after with the same semester/system/campus scope.
8. Inspect `EXPLAIN (ANALYZE, BUFFERS)` for the hot class query and confirm the new index is selected under realistic data volume.

### Index verification SQL

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'ix_academic_classes_training_scope',
    'ix_academic_subject_delivery_training_scope'
  )
ORDER BY indexname;
```

### Migration verification SQL

```sql
SELECT version_num FROM alembic_version;
```

Expected:

```text
0062_v25_9_16_7_2_64_40
```

## 12. Priority backlog

### P1 — next engineering batch

- Rewrite `list_teacher_subjects()` to DB-side page/aggregate instead of `.all()` + Python pagination.
- Review the remaining static query-hotspot blockers, starting with Training Operations/Analytics paths.
- Verify and right-size PostgreSQL pool budgets across all API/Celery processes.
- Add dependency/SBOM vulnerability scanning to CI.
- Add normalized-route HTTP/Celery metrics and alerts.
- Decide PDB/HPA/startupProbe from real cluster metrics.

### P2

- Consolidate CSS/hotfix layers.
- Review 8–10 px meaningful text and keyboard focus contracts across 360/768/1024 px layouts.
- Split large backend/frontend modules by domain.
- Design NetworkPolicy after documenting exact east-west/egress dependencies.
