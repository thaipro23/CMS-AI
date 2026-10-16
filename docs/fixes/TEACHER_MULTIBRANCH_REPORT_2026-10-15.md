# Teachers teaching in both Poly and PTCD

The `campus_snapshots exhausted` failure rejected valid assignments because
the scheduled report compared the class branch with `academic_teachers.branch`.
A teacher is unique by username across both systems, while AP previously
overwrote that profile field with whichever branch synced last. The earlier
coordinator delivery fix (`6339043`) did not address this separate business rule.

## Corrected behavior

- Retain one teacher identity. AP remembers observed branch/campus profiles in
  existing JSON metadata, preserves unrelated metadata, and stops flipping a
  shared person's scalar branch/campus. An ambiguous scalar becomes null.
  Historical profile metadata does not grant access; assignments remain authoritative.
- Refresh the teacher under a row lock before merging AP profiles so an ORM
  identity-map object cannot overwrite another worker's committed scopes.
- Build report labels from the requested teaching scope and class, including
  existing teachers whose legacy profile still names the other system. A report
  covering multiple campuses has no single campus label.
- Validate assignment branch, term, subject and campus against the class rather
  than treating the person's profile branch as an exclusive membership. Missing
  legacy assignment branch/campus inherits the class context. Explicit conflicts
  still fail; an empty frozen class set never validates unrelated classes.
- When AP corrects a class's subject/block, remove obsolete AP-owned assignment
  contexts only after the replacement persists. Preserve non-AP assignments and
  partial imports without a confirmed replacement.
- Keep snapshot scope validation strict. The built teacher row must explicitly
  carry the scheduled branch, and its classes/students stay within that scope.
  Materialized report keys advance to v3, bypassing old profile-based rows.

No schema migration, bulk teacher-branch rewrite, CMS-FPT change or frontend
rebuild is required. Existing teacher IDs and usernames are preserved.

## Verification

The new tests exercise both AP branch orders, a repeated import, already-existing
opposite teacher profiles, separate class/student sets and snapshot validation,
two-session stale profile merges, AP subject correction, lite/detailed reports
across campuses, invalid assignment contexts, frozen empty scopes, and old cache rows.
The corresponding AP, aggregation, context and stale-ORM cases failed against
their original implementations before the fixes.

Targeted AP/report/cache/access/snapshot tests: 72 passed. Daily pipeline and AP
contract tests: 53 passed. Lint F401/F821/E9 and whitespace checks pass.

The fresh original full-suite baseline has 313 failed, 1158 passed, 15 skipped.
The final full suite has 311 failed, 1174 passed, 15 skipped. Comparing every
failed test name found no new failures; the two removed failures are the stale
snapshot contract tests described below. The suite is not fully green.
Its named failures are in `QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt`.
Two existing `test_null_teacher_branch_inherits_class_branch[poly/ptcd]` tests
were corrected to require explicit scope on an already-built snapshot; the new
import-to-report tests cover inheritance from a shared teacher's model profile.
These are different boundaries: a nullable person profile is valid, while a
snapshot missing its projected branch remains invalid.

## Deployment and acceptance

Deploy the CMS-AI backend and Celery workers consistently from the updated
`feat/import-quiz-cms-old-su26` branch. Production deployment and job execution
were not performed from this workspace.

After deployment, check the affected report scopes:

- Poly term `1546bce8-f074-4bb3-916f-71a6d0da3445`.
- PTCD term `c75c7339-c22a-4413-bcce-9a5bdc365063`.

A teacher with assignments in both systems must appear in each relevant report,
with only that scope's classes and students. The supplied teacher IDs must no
longer fail merely because their profile names the other system. Genuine
assignment context conflicts still require AP reconciliation or correction.

A daily root already terminal with `campus_snapshots_exhausted` does not become
running when code is deployed. The existing `resume_daily_academic_pipeline`
helper accepts transport failures only; sending its root task again does not
reopen a business-exhausted run. Inspect the current root and its snapshot
attempts before choosing recovery. Do not clear audit history, mark failed
snapshots completed, or reuse the earlier transport-failure resume command as
if it handled this case. Subsequent scheduled runs use the corrected builder.
