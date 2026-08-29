# v25.9.16.7.2.35 — Analytics Post-Ingest Recalculate Orchestrator

## Summary

This release makes learning behavior analytics self-updating after tracking.log ingest without recalculating the whole term every minute.

## What changed

- `run_ingest(...)` now collects impacted `course_id`/`username` pairs only from newly inserted tracking events.
- Added `enqueue_post_ingest_recalculate_jobs(...)` in `LearningAnalyticsCoreService`.
- Course-to-class resolution order:
  1. `AcademicClassCourseMapping` direct class mapping.
  2. `AcademicCourseMapping` fallback by term/subject/block/campus/branch.
- Reuses `AcademicClassSyncJob` with `job_type='learning_analytics_recalculate'`.
- Enqueues class-level jobs, not student-level jobs.
- Production guards:
  - skip if class already has queued/running recalculate job;
  - skip if class is inside cooldown;
  - cap jobs per ingest run;
  - respect global active analytics job limit.
- Ingest checkpoint `stats_json` stores compact `post_ingest_recalculate` summary.

## New settings

```env
ANALYTICS_POST_INGEST_RECALCULATE_ENABLED=true
ANALYTICS_POST_INGEST_RECALCULATE_COOLDOWN_SECONDS=900
ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=10
```

## Safety

Ingest can still run every 60 seconds. Recalculate is debounced and class-scoped, so a large term does not rebuild all 15,000 enrollments every minute.

No migration.
