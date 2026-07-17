# Batch 20 — CMS RollNumber identity sync hardening

## Canonical policy

- Student CMS/Open edX username is exactly `AcademicStudent.student_code` / RollNumber.
- Case is preserved for new users (`PH12345` remains `PH12345`).
- Lookup is case-insensitive, so an existing legacy `ph12345` account is reused.
- Synced email is used; only when absent is `<RollNumber>@fpt.edu.vn` generated.
- Missing RollNumber blocks create, resolve-as-student, enrollment, and learning sync.
- AP username remains diagnostic metadata only and is never a student username fallback.

## Cross-layer changes

### AI Server backend / worker service

- Added `_student_rollnumber()` and preserved canonical case.
- Explicit `missing_student_code` mapping status for invalid AP records.
- Removed AP username fallback from resolve, enrollment, and learning-result correlation.
- Legacy matched AP-username mappings are re-resolved automatically instead of being treated as complete.
- Enrollment accepts only matched mappings whose Open edX username equals RollNumber case-insensitively.
- Worker uses the same service workflow, so no separate worker payload path remains.
- Exact RollNumber match methods now retain full mapping confidence; missing-code states clear stale active mapping flags.

### Open edX connector plugin

- Student rich payload username is derived only from `student_code`.
- Existing users are queried case-insensitively.
- New student usernames preserve RollNumber case.
- `_ensure_cms_user()` performs an additional `username__iexact` pre-check to prevent case-variant duplicates.
- Direct connector enrollment calls without RollNumber return `skipped_missing_rollnumber`.

### Identity reconciliation

- Canonical display value keeps case while comparisons use a normalized lookup key.
- Manual mapping no longer defaults Open edX username to AP username.

## Deployment note

Both AI Server containers and the Open edX connector plugin must be deployed. Restart/recreate backend and worker after deploying AI Server, then rebuild/reinstall the connector plugin in LMS/CMS according to the existing Tutor deployment process. Existing failed jobs are not replayed automatically.

No database migration was added. Tests/build were not run per project instruction.
