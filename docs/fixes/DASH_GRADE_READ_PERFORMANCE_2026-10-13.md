# DOM1021 grade reads and BUS1052 workspace timeout

Production profiles supplied on 2026-10-13 show DOM1021 summary taking
34.04 seconds, with 280 component normalizations consuming 33.33 seconds;
the nine completed SQL queries consumed 0.067 seconds. Recent grade jobs
took 39.52 and 44.87 seconds with negligible queue wait. BUS1052 behavior
summary and rows each failed at the 10-second PostgreSQL statement timeout
on the standalone scoped MAX(event_time) query.

## Changes

- Deduplicate normalized component identities with a dictionary instead of
  rescanning all existing components for every duplicate. Preserve the first
  actual score, including zero, and replace only planned shells.
- Normalize each snapshot once per synchronous class roster/summary read.
  Clear the ContextVar cache in finally; return independent row dictionaries.
  Subsequent requests read current data. Sync writes do not use this cache.
- Compute count, distinct users, and latest tracking timestamp in one scoped
  aggregate. This removes the standalone MAX query that timed out, without
  increasing the timeout or changing course/roster filters.
- Compute workspace diagnostics once and reuse them in summary and rows.

Grade calculation rules, permissions, response fields, and reset behavior
remain unchanged. No database migration is needed.

## Verification

- 39 focused tests passed, including grade/component contracts, real workspace
  execution, aggregate scoping and empty scopes, cache cleanup and freshness.
- Full backend suite: 1149 passed, 14 skipped, 313 failed. Failed test names
  exactly match the committed pre-existing baseline in
  QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt; there are no new failures.
- Independent review: 200 randomized payloads produced identical old/new
  normalization output; concurrent read scopes stayed isolated.
- Synthetic 40-learner benchmark using the actual summary method and equal
  database-boundary fixtures: 18.6121 seconds before, 0.2764 seconds after;
  normalizations 280 -> 40; identity checks 4,974,040 -> 17,800. The entire
  summary output matched. These are local fixture timings, not production
  latency measurements.

## Deployment and acceptance

Deploy the CMS-AI backend and grade-processing workers from this commit on
feat/import-quiz-cms-old-su26. No CMS-FPT, frontend, or MFE rebuild is required
for this patch. No production rollout was performed during implementation.

After rollout, rerun the same DOM1021 score job and profile both students and
learning-summary reads. Compare grades and quiz columns with the pre-rollout
results. Open the BUS1052 workspace for class
667302cd-10c6-472d-8d42-6aacef51b57f with and without
course_id=course-v1:FPL+BUS1052+FA26 and confirm HTTP 200. Inspect the combined
aggregate plan and runtime on production PostgreSQL: the live query plan and
latency have not been verified locally.
