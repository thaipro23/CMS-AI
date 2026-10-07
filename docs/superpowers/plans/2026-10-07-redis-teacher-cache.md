# Redis teacher dashboard and root discovery

**Goal:** Reduce repeated teacher overview reads without crossing access scopes, and resume the correct daily pipeline without a supplied UUID.

**Architecture:** Keep PostgreSQL authoritative. Add a 45-second page/KPI cache, fingerprint current access decisions and every report argument, invalidate after committed academic changes. Reuse bounded Redis pools per process. Cache may use an independent endpoint; security and coordinator locks keep the existing endpoint. Redis cache errors fall back to the original report. Existing continuation recovery remains unchanged.

**Constraints:** Preserve report fields, branch boundaries, fresh bypass, drill-down/export behavior and live email statistics. No migration, student score edits, automatic production resume or CMS-FPT changes. Root discovery uses the Vietnam run date, exact root type, and refuses ambiguity; existing resume safeguards apply under the coordinator lock.

**Tasks:**
1. Add regressions for cache isolation, invalidation, fallback, pool reuse and date-based discovery; demonstrate failures first.
2. Implement `core/redis_client.py`, `services/academic/teacher_report_cache.py`, integrate existing Redis consumers and report workflow.
3. Add root discovery inside `resume_daily_academic_pipeline`; update deployment command and environment examples.
4. Run targeted tests, actual Redis integration and the existing backend CI suite. Review changes and publish to the authorized branch.

**Review focus:** Authorization before cache lookup; no stale entry resurrection during invalidation; no database mutation on ambiguous discovery; no pool shutdown by coordinator cleanup; no eviction policy changes on the broker Redis.
