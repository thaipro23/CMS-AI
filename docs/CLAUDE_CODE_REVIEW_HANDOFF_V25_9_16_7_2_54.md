# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: AI Server / Open edX CMS `v25.9.16.7.2.64.12 — RollNumber Identity Migration Assistant`.

## Focus areas for review

1. `GET /api/academic/identity/rollnumber-migration`
   - Must be read-only.
   - Must enforce the caller academic/campus/class scope.
   - Must not create/delete Open edX users, mappings, snapshots, enrollments, or jobs.

2. `AcademicService.rollnumber_identity_migration_report(...)`
   - Correctly treats RollNumber/student_code as canonical CMS username.
   - Flags legacy AP username/email mappings as blockers.
   - Does not auto-resolve ambiguous or duplicate RollNumbers.

3. `scripts/rollnumber-identity-migration-report.sh`
   - Should only call read-only API.
   - Should export JSON/Markdown evidence.

## Non-goals

- No new Alembic migration.
- No FEID/Google auth bridge.
- No destructive cleanup in this version.
- No classifier changes.

## Suggested commands

```bash
./scripts/claude-code-review-pack.sh
./scripts/uat-build-gate.sh
```
