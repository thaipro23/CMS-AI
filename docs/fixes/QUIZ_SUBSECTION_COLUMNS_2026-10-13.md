# Quiz columns follow graded subsections

Production DOM1021 FA26 has 16 graded Quiz subsections and one Final test.
The Oct 13 structure dump showed 34 planned Connector rows: those 17
subsections plus their 17 Unit children. Sorting two Final rows first and
numbering unnamed Unit children produced Quiz 3–18. Dash merged those with
the real Quiz 1–16, yielding two extra columns.

The Connector now collects only graded `sequential` Quiz/Final assignments,
keeps their usage keys, and labels Final separately without a Quiz number.
Child Units/problems do not become assignments. All current assignments are
returned for each learner, including null shells for unattempted assignments.
Actual grades remain authoritative and are joined to shells by usage key;
valid zero points are retained and missing points are not fabricated.

Dash builds a class assessment plan from the new sync responses only.
Previously it also merged old snapshots, which resurrected phantom Quiz
17/18 even after the Connector response was corrected. Existing snapshots
are replaced by the normal learning-sync workflow; no direct data repair or
reset of student attempts is required.

Learning sync requires Connector `.109` or newer and an explicit
`assessment_plan_complete=true` on every returned learner. A course lookup
error or any unreadable descendant marks the plan incomplete. Dash refuses
to persist that refresh, preserving previous snapshots instead of shrinking
the plan and inflating averages. Mixed old/new LMS pods also fail this check.

## Deploy and verify

1. Build/deploy Open edX with Connector runtime `25.9.16.5.109`, package
   `0.1.19`. Deploy this before the Dash change: older Connectors do not
   reliably return a complete current subsection plan.
2. Deploy the Dash backend and workers from this fix. No frontend or MFE
   change and no new database migration are needed for this column fix.
   The earlier Unit Reset `0.4.18` still requires its own migration `0003`.
3. Run the read-only DOM1021 structure diagnostic again. Expected:
   `planned_components=17`, all `block_type=sequential`, Quiz 1–16 plus Final.
4. Click **Cập nhật điểm** for the affected class and wait for the forced
   learning-sync job to finish. Its full-roster identity/enrollment/response
   guards remain in force. Then reload the class: exactly 16 Quiz columns
   and one Final column should remain.
5. Compare PH56940's actual component scores and sync timestamps with the
   Connector payload. Full marks on the 17 assignments must remain 10/10
   in Dash regardless of the LMS's unrelated 200% grading-weight issue.

The patch does not change LMS points, randomize ItemBank selections or reset
attempts. Production rollout and complete image integration are not performed
from this development workspace.

## Verification

- DOM1021 nested structure regression fails with 34 rows before the fix and
  passes with 17 after it. Tests also cover ungraded/scored child exclusion,
  Final numbering, courses without Final and zero-valued actual grades.
- Actual Dash learning sync with SQLite snapshot persistence replaces an old
  18-Quiz snapshot with 16 Quiz plus Final and preserves full marks at 10/10.
- Complete standalone Connector suite: 57 passed.
- Focused Dash score/average/component contract tests: 30 passed.
- Full Open edX image/runtime integration and live production payload checks
  remain deployment acceptance steps.

The full Dash backend suite is not green: 313 failed, 1141 passed, 14 skipped.
The unchanged parent has exactly the same 313 failed test names (1137 passed,
14 skipped). No new failed test names were introduced. The complete named
failure list is in `QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt`.
