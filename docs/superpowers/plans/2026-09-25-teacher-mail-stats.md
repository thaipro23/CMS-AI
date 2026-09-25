# Teacher Mail Statistics and Creator Username Plan

## Spec

- Place mail statistics inside **Vận hành đào tạo → Quản lý giảng viên CMS**.
- Teacher list: show the total number of successfully sent progress-reminder emails for the teacher's classes.
- Teacher class list: show the successfully sent total for each class.
- Class student list: show the confirmed sent count and latest confirmed sent time for each student.
- Never call a provider-accepted message "read" or "opened"; the product label is **Mail đã gửi**.
- Preserve numeric `requested_by` values for audit/RBAC while showing the corresponding username in the Jobs UI.
- Keep Poly/PTCĐ/campus scope isolation and do not expose raw email addresses or message bodies.

## Global constraints

- Reuse `AcademicBulkOperationJob(job_type='progress_reminder_email')`; no migration or duplicate mail-statistics table.
- Count only provider-confirmed successful sends. Do not infer student attribution for legacy aggregate-only sessions.
- Aggregate mail data with bounded bulk queries; no per-row database queries.
- Existing API fields remain backward compatible.

## Task 1: Mail statistics aggregation service

**Files:**
- Create: `backend/app/services/academic/progress_email_stats.py`
- Test: `backend/app/tests/test_academic_progress_email_stats.py`

**Produces:** class totals, per-student totals/latest timestamps, and teacher totals derived from class assignments.

1. Write failing tests for confirmed deliveries, failed deliveries, legacy aggregate-only jobs, duplicate teacher assignments, and scope filters.
2. Run the focused tests and confirm the expected failures.
3. Implement the smallest aggregation service that passes.
4. Run the focused tests green.

## Task 2: Enrich teacher and student APIs

**Files:**
- Modify: `backend/app/api/routes/academic.py`
- Modify: `backend/app/schemas/academic.py`
- Modify: `backend/app/services/academic/roster.py`
- Test: `backend/app/tests/test_academic_progress_email_stats_api.py`

**Consumes:** Task 1 aggregation service.

**Produces:**
- teacher item `progress_email_sent_count`
- class item `progress_email_sent_count`
- student item `progress_email_sent_count`, `progress_email_last_sent_at`

1. Write failing API/service tests for the three response levels and RBAC-isolated scope.
2. Run them red.
3. Enrich report responses after cache/lite/full report construction and enrich only the current student page.
4. Run focused backend tests green.

## Task 3: Display mail counts in the requested CMS screens

**Files:**
- Modify: `frontend/types/index.ts`
- Modify: `frontend/app/teacher-management/TeacherManagementPlatformPage.tsx`
- Modify: `frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx`
- Modify: `frontend/app/student-management/classes/[classId]/page.tsx`
- Test: relevant frontend tests under `frontend/**/__tests__` or existing page contract tests.

1. Write failing UI contract tests for teacher, class, and student labels.
2. Run them red.
3. Add **Đã gửi N mail** to CMS teacher identity, a **Mail đã gửi** class column, and a **Mail đã gửi** student column with latest time.
4. Do not show the fields on Udemy screens.
5. Run focused frontend tests green.

## Task 4: Show creator username without replacing the audit ID

**Files:**
- Modify: `backend/app/api/routes/users.py`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/jobs/page.tsx`
- Modify: `frontend/types/index.ts`
- Test: backend identity-label tests and frontend Jobs tests.

1. Write failing tests for bulk username lookup, system actor handling, missing-profile fallback, and Jobs display.
2. Run them red.
3. Add a bounded authenticated username-label endpoint backed by `AIUserProfile` and update Jobs to resolve visible creator IDs in one request.
4. Display username first; fallback to `requester_context.username`, then `Người dùng #<id>`, while scheduler actors display `Hệ thống`.
5. Run focused tests green.

## Task 5: Verification and delivery

1. Run the full relevant backend and frontend suites, lint/typecheck/build as available.
2. Review the whole diff for privacy, RBAC scope, aggregation correctness, and query growth.
3. Commit the changes on `impl/unified-academic-daily-pipeline`.
4. Push fast-forward to `origin/feat/import-quiz-cms-old-su26` only when GitHub authentication is available.

## Review focus

- No Poly/PTCĐ or campus leakage.
- No raw addresses/body in responses or logs.
- Only confirmed successful provider deliveries count.
- Cached teacher reports receive live mail totals without rebuilding the report cache.
- Legacy jobs do not fabricate per-student history.
- Creator lookup cannot produce N+1 queries.
