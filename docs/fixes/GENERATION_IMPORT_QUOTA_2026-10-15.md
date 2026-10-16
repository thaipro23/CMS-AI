# AI generation quota is independent of imported question inventory

The settings limit applies to AI-created questions per chapter, rather than
every question stored in the chapter. Previously both the backend generation
guard and the workspace button subtracted imported questions from the quota.

| Imported | Already created by AI | AI capacity remaining with limit 100 |
| ---: | ---: | ---: |
| 30 | 0 | 100 |
| 150 | 0 | 100 |
| 30 | 20 | 80 |
| 30 | 100 | 0 |

Importing 30 and generating 100 therefore leaves 130 questions in the bank.
Manual authoring and imports do not spend the AI quota. AI questions in pending,
approved, rejected and draft-error states still count, preserving existing
review-state and retired-question rules.

## Change

- Separate total chapter inventory from generated chapter counts. Keep existing
  total fields intact, add `chapter_generated_count` to readiness and
  `generated_question_count` to generation preview, and use AI counts for
  preview, worker enforcement and the workspace controls. The preview response
  schema explicitly retains the new generated count for frontend consumers.
- Apply the same origin filter to legacy course cost/quota checks and the
  course-policy API so its counters agree with enforcement.
- Recognize explicit import/manual authoring and provider markers, plus
  historical imports whose authoring mode defaulted to AI. Distinguish those
  from actual AI questions generated from legacy quiz material chunks using
  persisted generation provenance. Such generated questions still spend quota.
- Preserve classified authoring origin before carry-over or term cloning
  replaces source identifiers, so imported questions remain imports. Historical
  copies with retained lineage resolve their original question by primary key
  in the same SQL query, without rewriting rows or loading ancestors one by one.
- Clarify settings and workspace labels: AI generation usage, total inventory,
  and remaining AI generation capacity are separate values. Review/publish
  inventory still includes imported questions.

The configured limit values and per-job rules are unchanged. No migration or
question-data rewrite is required. Rebuild/deploy the CMS-AI frontend, backend
and generation workers together from `feat/import-quiz-cms-old-su26`.
No CMS-FPT/Open edX rebuild is required. Production deployment was not performed.

## Verification

- Reproduced the original 30-import/70-remaining rejection before fixing it.
- 15 real SQLite workflow tests pass, including 150 imported questions,
  30 imported plus 100 generated questions, mixed AI review states, course
  quota/policy counters, AI generation from legacy material chunks, carry-over,
  subject-offering cloning, and historical copies with retained lineage.
- Five regression cases execute the workspace's actual TypeScript quota and
  button calculations; all 25 frontend tests pass.
- Frontend typecheck, lint and production build pass.
- Changed backend modules pass F401/F821/E9 checks; the existing parent
  `question_bank_service.py` has 18 unchanged unused-import findings, with
  no new lint issues. F821/E9 and whitespace checks pass.
- Final full backend suite: 1189 passed, 15 skipped, 311 failed. Every failed
  test name exactly matches the parent `762a1ff` baseline; no new failures.
  The suite is not fully green. Named baseline failures are documented in
  `QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt`, excluding the two obsolete
  `test_null_teacher_branch_inherits_class_branch[poly/ptcd]` cases already
  corrected by the preceding teacher-scope fix.
- Independent review confirmed the SQL origin lookup compiles with correct
  PostgreSQL correlation and found no remaining blockers. Live production
  acceptance remains to be checked after deployment.

Acceptance: on a draft chapter with 30 imported questions and no AI questions,
the generation dialog must show AI usage 0/100, allow 100, show an estimated
inventory of 130, create those 100, and then reject another AI question while
leaving import available.
