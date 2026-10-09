# Learning analytics audit fix — 2026-10-09

## Scope and baseline

The 2026-10-07 audit covered 83 roster students in LOG104, GD2102 and VIE108. Only 79 behavior snapshots existed. Quiz-only students could receive positive watch-then-quiz evidence, shared courses reused another class's inferred dates, and repeated high completion with very little measured watch often remained NORMAL. All 4,644 captured quiz item submissions lacked a content version.

The CMS-AI review branch is based on `9c054567684d111b34d94a55bbc8639f25a3cecf`, including the latest class assessment plan and score-sync changes. The accompanying CMS-FPT branch is based on `5c7887a`, preserving its grade-isolation and quiz-duration implementation. These changes introduce no schema migration and do not write official grades or official learning snapshots.

## Resulting behavior

- Inferred deadlines are resolved using the requested class. Explicit quiz overrides retain priority. Shared course/student progress is projected onto the class on reads and behavior aggregation, without changing stored ORM rows during reads.
- WATCH_THEN_ATTEMPT_PROBLEM requires a counted watch segment ending before the quiz submission. A first-play marker plus later cumulative watch is insufficient. Legacy positive reasons without pre-submit evidence are excluded. No-video students receive no video-based real-learning points.
- Repeated, measurable high completion with very low watch and strong suspicious-video coverage produces POSSIBLE_ANOMALY / TEACHER_REVIEW. This is an evidence review label, not a finding of misconduct. Confidence and behavior scores are heuristics on a 0–100 scale, not probabilities.
- Repeated play notifications preserve already observed watch segments and cannot split a long passive segment to bypass its cap. Aware snapshot timestamps are normalized to UTC before comparison with tracking events.
- API/UI expose stale snapshots and missing roster coverage. One fresh student no longer hides older results from other students.
- When available, the official component snapshot supplies the session quiz score. A partial tracking problem score does not override that whole-quiz score. Tracking-only scores remain partial observations; official score storage is unchanged.

## Quiz telemetry and integrity

The LMS plugin wraps the actual `xmodule.capa_block.ProblemBlock.publish_unmasked` hook. Server problem_check events gain a content-addressed definition version, normalized response identity and vertical quiz scope. Generated CAPA response/input IDs and group-label references do not make equivalent clones different. Changes to definitions or variants remain distinct. Metadata failures do not reject a native submission or change its answers, grades, timer or timeout auto-submit.

Successful start/reset views emit the actual persisted session ID and start time. Refreshes reuse the nonce and do not extend expiry. HTTP access logs and browser start/reset requests do not prove success. Retained legacy timing/reset evidence without provenance is treated as unknown. Assignments rendered before timer start belong to that same first attempt.

Problem events, companion grades and known assigned clones are grouped under their quiz vertical. Comparable questions count response slots, while timing requires genuinely distinct observations. Whole-form and timeout submission bursts remain neutral context.

The reference population is configurable with `ANALYTICS_QUIZ_REFERENCE_PEOPLE_MIN`, default **12 other students per comparable question**, minimum 12. This changes the previous default of 30 so cohorts of 20–28 can be evaluated when all other gates are met. This policy is not an empirically validated accuracy guarantee; set 30 to retain the previous population requirement. Pair review still requires at least eight comparable responses, 80% matching answers, three shared rare incorrect responses, six independent non-burst timing observations and consistent direction/lag. Missing versions, question identity, baseline population and timing have separate reason codes.

Historical versions are not fabricated from current course content. Raw logs already outside retention and missing historical definitions cannot be reconstructed; affected quiz results remain INSUFFICIENT_DATA.

## Verification

- CMS-AI CI unit selections: 316 tests plus six release checks passed; focused analytics and current official-grade/completion suites also passed.
- CMS-FPT standalone tests: 15 passed, including real timer persistence on start/refresh, successful and failed reset boundaries, duration edits, grade-isolation targeting and real CAPA clone identities.
- Backend compile and Ruff fatal checks passed.
- Full backend comparison: both the unchanged `9c05456` baseline and the fix have the same 313 historical failures. There are no newly introduced failures; the fix has 39 additional passing tests.
- The two PostgreSQL/Redis integration smoke tests require services unavailable in this workspace. The existing GitHub PR workflow supplies those services; its results must be reviewed before merge.
- The CMS-FPT ZIP is rebuilt from source and checked for source parity, version 0.4.17 and cache-file hygiene.

Frontend typecheck, targeted analytics lint and production build passed after restoring an isolated dependency installation.

The uploaded audit was loaded into disposable SQLite databases and recalculated from retained video/quiz aggregates and official component snapshots. This is not a full raw-telemetry replay: exported raw rows omit context and some are truncated, so quiz ingestion was deliberately skipped. Quiz integrity was evaluated from the retained item history. Reconstructed mapping columns came only from the exported roster; no missing content versions were invented.

| Class | Before snapshots / roster | After snapshots | Teacher-review labels | Missing-data labels | Normal labels |
| --- | --- | --- | --- | --- | --- |
| LOG104 | 16 / 20 | 20 | 4 | 6 | 10 |
| GD2102 | 28 / 28 | 28 | 14 | 9 | 5 |
| VIE108 | 35 / 35 | 35 | 0 | 30 | 5 |

All 83 roster students were materialized. No-video/positive-learning contradictions were zero in all three classes. Official learning snapshot contents were hashed before/after and remained identical. The VIE108 first inferred deadline is now 2026-09-21 rather than the other class's November anchor. All 4,644 legacy items still lack content versions; the 5,195 canonical retained quiz results remain INSUFFICIENT_DATA. Canonicalization removes obsolete duplicate derived results without deleting item history. These offline labels describe available evidence, not verified cheating or deployed results.

## Deployment after merge

Deploy CMS-AI backend, analytics worker and frontend together. Deploy CMS-FPT unit-reset plugin **0.4.17** to the LMS. The independent, older CMS-AI bundle is bumped to **0.4.14.8**; it must not replace the newer CMS-FPT implementation. `UNIT_RESET_QUIZ_ANALYTICS_ENABLED` defaults to true and can disable the additional telemetry.

Before relying on new quiz comparison, verify `ProblemBlock.publish_unmasked._acms_quiz_analytics` in the deployed LMS, then perform start, refresh, submit and successful reset. Check scoped nonce/started_at and problem_check content_version/question_hash, alongside unchanged official scores and timer expiry. Offline tests exercise the native publish boundary and standalone Django persistence; a full deployed LMS integration run is still required.

Recalculate each audited class through the existing class analytics UI/API without a username filter, wait for the worker jobs, then collect another audit:

| Class | Class ID | Course |
| --- | --- | --- |
| LOG104 | 2427f084-61c3-4f65-8db4-5c5cbbc2f785 | course-v1:FPL+LOG104+FA26 |
| GD2102 | 8d9cde79-c120-45c0-ba48-08e2c85c4341 | course-v1:FPS+COM1091+FA26 |
| VIE108 | 7c0fc072-c6a3-47ee-a02b-b300b7718b35 | course-v1:FPL+VIE108+FA26 |
