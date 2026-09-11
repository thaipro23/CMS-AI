# MASTER CONTEXT — DASH CMS

Updated: 2026-09-10 (Asia/Bangkok / UTC+7)

## A. Project Identity

- Dash CMS repository: `https://github.com/thaipro23/CMS-AI`
- Canonical working branch: `feat/import-quiz-cms-old-su26`
- Open edX/CMS-FPT repository: `https://github.com/thaipro23/CMS-FPT`
- Canonical Open edX branch: `fpt-indigo-ui`
- Working source for AI sessions: latest handed-off ZIP. Do not reset/revert it from remote Git.
- This ZIP does not contain `.git`, so HEAD/working-tree status cannot be derived locally. Git state must not be guessed.

## Source-of-truth priority

1. Latest direct user instruction.
2. Actual source in latest ZIP/working copy.
3. Runtime evidence from Kubernetes/API.
4. This MASTER CONTEXT.
5. Older release/context documents.

## Current AP Sync Contract

### Business rules

- Campus list for AP sync is managed manually in Dash CMS `/premises`.
- Do **not** replace the Dash/manual campus list with automatic `/get-campus` discovery.
- The current PTCĐ sync scope intentionally uses the 18 campuses selected/configured in Dash.
- `/get-campus?product=PTCD` may return a different/larger catalog, but it is not the authoritative sync-scope source.

### Runtime incident — Run `04bea2bd-cf9a-452e-8497-532351e62119`

Observed on 2026-09-08:

- `status=completed`
- branch `ptcd`
- term `Fall 2026`
- 18 Dash campuses x 20 selected subjects = 360 AP requests
- classes/students/teachers/subjects imported: 0
- errors: 360
- every `/get-data-cms` request returned HTTP 400
- AP response body: `campus_code Không được bỏ trống`

Root cause:

- `APAcademicClient.get_division()` sent JSON field `campus`.
- Current AP `/get-data-cms` contract requires JSON field `campus_code`.

Bounded fix:

- `backend/app/services/ap_academic_sync.py`
- request body now sends:
  - `campus_code`
  - `term_name`
  - `subject_code`
- campus selection/discovery is explicitly locked to the manual Dash `/premises` catalog; AP `/get-campus` is not used to populate AP-sync options or the fallback for `sync_scope=all`.

Regression contract:

- `backend/app/tests/test_academic_ap_internal_api.py` already asserts the `campus_code` JSON payload.
- `backend/app/tests/test_ap_sync_manual_campus_contract.py` adds a static bounded regression check.

### Remaining AP sync issue

The run can still end as `completed` when every subject request fails. This status behavior was identified but is **not changed in this task** because the user requested only the payload fix plus the premises UI change.

## `/premises` Campus Management

Business rule:

- Campus catalog remains manually managed in Dash CMS.
- Keep manual Add/Edit/Delete behavior.
- Do not provide a `/premises` action that refreshes/imports campuses from AP/FU API.

2026-09-08 change:

- Removed the `Cập nhật cơ sở` button/refresh wrapper from `frontend/app/premises/layout.tsx`.
- Removed the now-unused `.premises-catalog-refresh*` CSS from `frontend/styles/fa26-layout-hotfix.css`.
- Kept `Thêm cơ sở thủ công`, Edit, Delete, filters, and manual data source behavior in `frontend/app/premises/page.tsx`.
- The separate refresh action on `/ap-sync` was left in place because the user explicitly scoped button removal to `/premises`; its campus options now come from Dash `/premises`, not AP `/get-campus`.
- `/ap-sync` KPI text now states `Lấy từ danh mục cơ sở Dash CMS`.

## Tests for this task

- PASS: `pytest -q backend/app/tests/test_ap_sync_manual_campus_contract.py` -> 3 passed.
- `backend/app/tests/test_academic_ap_internal_api.py` could not be collected in this execution environment because the local Python environment lacks `psycopg`; this is an environment dependency failure, not a test assertion failure.
- Frontend npm build/typecheck not run because `frontend/node_modules` is absent in the handed-off workspace.

## Current Work

CURRENT TASK: Fix campus-owner scope in Training Operations: automatic PTCĐ/TK filter selection, campus-owned subject/class access, and correct role display.

STATUS: SOURCE COMMITTED TO CANONICAL BRANCH / REMOTE SOURCE RE-READ / NOT DEPLOYED OR PRODUCTION-VERIFIED.

CURRENT HEAD AFTER THIS UPDATE: set by GitHub contents commit following `105e3026cce5a2a6239f76c2704730469d4c6c15`; re-read branch before deployment rather than assuming this document's SHA is still HEAD.

FILES IN CURRENT FIX:

- `backend/app/services/academic/access.py`
- `backend/app/api/routes/academic_scope.py`
- `backend/app/api/router.py`
- `frontend/components/layout/AppShell.tsx`
- `frontend/hooks/useAcademicTableState.ts`
- `frontend/app/student-management/StudentManagementPlatformPage.tsx`
- `frontend/app/student-management/subjects/[subjectId]/classes/page.tsx`
- `backend/app/tests/test_campus_owner_training_scope_contract.py`
- `MASTER_CONTEXT_DASH_CMS.md`

NEXT ACTION:

1. Build backend + frontend image from the canonical branch.
2. Deploy the new image(s) to production and verify runtime image digests/tags.
3. Login with a concrete `CAMPUS_OWNER` account such as the reported TK owner.
4. Confirm the account lands on `branch=ptcd&campus=tk` before protected academic list requests are sent.
5. Confirm `/api/academic/training-scope` reports the assigned campus and branch.
6. Re-run the reported `/api/academic/subjects/<subject_id>/classes?...campus=tk&branch=ptcd...` request and confirm 200 with only TK classes.
7. Confirm the user chip/popover shows `Chủ cơ sở · TK`, not legacy `Người xem - chỉ xem`.

## Production claim

- Source updated: YES.
- GitHub commits/push: YES on `feat/import-quiz-cms-old-su26`.
- Remote source re-read: YES for the scope hook and affected student-management pages.
- Automated execution of the new static regression test: NOT RUN in this chat environment.
- Deployment: NOT DONE/NOT VERIFIED in this session.
- Production verification: NOT DONE.

## Update 2026-09-08 — Student/Analytics top-level section overlap

### Observed
- Production screenshots after a refreshed frontend image still showed top-level cards painting over the following card on:
  - `/student-management/classes/<classId>` (class action/workspace card overlapping the student list; intermediate KPI/context content effectively painted underneath the next section).
  - `/analytics/learning` (permission `ContentNotice` at the bottom of the filter/workflow card painted underneath the `Chọn môn` card).
- `/bank/quiz` constraint panel exists in current source (`ConstraintModeControls`) with default Single 50 / Multi 30 / Dropdown 20 / Text 0 / Numerical 0; that is a separate deployment/bundle verification concern, not the overlap root cause.

### Root cause
- `frontend/styles/production-ui.css` forces `.page-stack { display: grid !important; }`.
- The later shared `project-spacing-contract.css` intends page stacks to be flex columns, but uses `:where(...)` and no `!important`, so it cannot override the legacy `display:grid !important` declaration.
- Student/Analytics are fixed-height workspace scroll owners. Their long top-level cards can therefore be sized as legacy grid rows while child content still paints outside the row, producing visible section-on-section overlap.
- The repository already uses a route-scoped flex override for Bank hierarchy pages for the same legacy Grid behavior; the Student/Analytics fix follows that bounded pattern.

### Fix
- `frontend/styles/fa26-layout-hotfix.css` now forces only `.student-management-page` and `.analytics-learning-page` page stacks to `display:flex !important; flex-direction:column` with stretched, content-sized top-level children.
- Top-level `.academic-unified-card` rows on these pages are explicitly `height:auto` / `min-height:max-content` so they cannot be compressed into overlapping grid tracks.
- `frontend/tests/fa26-layout-hotfix.test.cjs` statically guards the scoped flex/content-sized contract.

### Verification
- PASS: `node --test frontend/tests/fa26-layout-hotfix.test.cjs` => 2/2.
- Browser/K8s visual verification still required after a newly tagged frontend image is rolled out.

### Related AP/premises decisions retained
- `/get-data-cms` request key is `campus_code` (not `campus`).
- AP sync campus scope is authoritative from the manually maintained Dash `/premises` catalog; do not auto-replace the 18 configured Dash campuses with `/get-campus` output.
- `/premises` no longer exposes the API-driven `Cập nhật cơ sở` wrapper; manual add/edit/delete remains.

## Update 2026-09-09 — Sticky horizontal rail for long tables

### User requirement
- On long wide tables such as class student lists, the horizontal scrollbar must stay reachable at the bottom of the viewport while the user is in the middle of the table.
- Users must not have to scroll to the final table row just to move horizontally.

### Root cause and fix
- `EnterpriseDataTable` already renders a synchronized `.enterprise-sticky-horizontal-scroll` for tables opting into `stickyHorizontalScroll`.
- `student-operations-visual-hotfix.css` defined the rail as sticky, but a later FA26 hotfix overrode it with `position: static !important`.
- `frontend/styles/fa26-layout-hotfix.css` now keeps the synchronized rail `position: sticky !important; bottom: 0 !important` for Student Management / Analytics.
- Regression test: `frontend/tests/enterprise-sticky-horizontal-scroll.test.cjs`.

### Git
- Relevant commits: `6b83975e6c96be0d2758554a62139d3c5659ba5d`, `3ccf65ed932b60048219b59bedb59cfffc21ae22`.

## Update 2026-09-09 — Manual dropdown OLX + Open edX feedback cleanup

### Observed
- A manually authored `dropdown_fill` question stores `[_____]` in `question_text`, but exported OLX split on the token and removed the token from the `<p>` prompt before inserting `<optionresponse inline="1">`.
- Open edX already renders `Correct:` / `Incorrect:` around choice feedback, while Dash fallback/explicit feedback could also start with `Đúng.` / `Sai.` / `Chưa đúng.`, creating duplicated status text such as `Correct: Đúng...` and `Incorrect: Chưa đúng...`.

### Root cause
- `backend/app/services/openedx_exporter.py` used `BLANK_TOKEN_RE.split(...)` and never reinserted the blank marker.
- The same exporter sent `choicehint` text verbatim, including correctness prefixes generated by `build_choice_feedback()` or entered explicitly.

### Bounded fix
- Direct manual authoring (`authoring_mode=manual` or `source_type=manual`) now reinserts the original `[_____]` token inside the `<p>` immediately before its inline `<optionresponse>`.
- Imported/legacy dropdown behavior is intentionally unchanged.
- Before emitting Open edX `choicehint`, exporter strips only a leading correctness status prefix: `Đúng`, `Sai`, or `Chưa đúng` (with common punctuation). The explanatory content is preserved.
- Applies to explicit and generated feedback; Open edX remains the owner of the `Correct:` / `Incorrect:` status UI.

### Files
- `backend/app/services/openedx_exporter.py`
- `backend/app/tests/test_openedx_exporter.py`

### Verification
- PASS: `DATABASE_URL=sqlite+pysqlite:///:memory: pytest -q backend/app/tests/test_openedx_exporter.py` -> 14 passed.
- A wider two-file run reached 26 passing tests; 5 unrelated worker-default tests could not run because this execution environment lacks the `celery` package.
- Generated manual dropdown OLX was manually inspected: `<p>` contains `[_____]` and the inline `<optionresponse>` remains adjacent.

### Git
- Source commit: `564a2312ab4a4ba8579c6bd4226f03db5616b85c` (`fix: preserve manual dropdown blanks and clean Open edX feedback`).
- Regression commit: `319c4b75cc6a3785e4f8afb1bf4db0d8806f8945` (`test: cover manual dropdown blanks and Open edX feedback cleanup`).
- Deployment/production verification: NOT DONE in this session.

## Update 2026-09-09 — Backend build compile failure in health route

### Observed
- Jenkins backend build reached `PYTHON COMPILE` and stopped before SonarQube with `SyntaxError: '(' was never closed` in `backend/app/api/routes/health.py:256`.
- Broken expression was `QueryHotspotService().report(max_items=max(1, min(int(max_items or 100), 300))`.

### Root cause
- The `report(` call was missing its final closing parenthesis. This is a syntax-only regression; no QueryHotspot business logic change was required.

### Fix
- `backend/app/api/routes/health.py` now uses `return QueryHotspotService().report(max_items=max(1, min(int(max_items or 100), 300)))`.
- Remote source commit: `f310f1ad299924b727c1bc70e32e85f04e373893` (`fix: close query hotspot health report call`).

### Verification
- Remote branch/file re-read confirms the corrected expression is present.
- Local handed-off source snapshot with the corrected expression passes `python -m compileall -q app` with exit code 0.
- Jenkins/Sonar rerun: NOT YET VERIFIED; rerun the pipeline from the new branch HEAD.

## Update 2026-09-10 — Campus-owner Training Operations scope, subject access, role label

### Production evidence before the fix
- A campus owner account scoped to campus `TK` under branch `ptcd` could reach Training Operations but the UI initially retained the generic `poly` default.
- The reported class-list request for a PTCĐ/TK subject returned HTTP 403 with `Bạn không được phân công hoặc phân quyền xem môn này`.
- The shell displayed the legacy effective role label `Người xem - chỉ xem` instead of the effective business assignment `CAMPUS_OWNER`.

### Root causes
- `AcademicAccessWorkflowService.assert_can_access_subject()` checked explicit subject ownership/AP teacher assignment but did not treat a subject as visible when it had classes in a campus owned by the actor.
- Training pages initialized `useAcademicTableState({ branch: 'poly', ... })`; scope resolution was asynchronous, so protected data effects could run before campus/branch normalization.
- App shell role text was based on the legacy `role` compatibility field instead of ranking the active business-RBAC assignments returned by `/rbac/me`.

### Fix contract
- `backend/app/services/academic/access.py`: a campus-scoped owner may open a subject only when an `AcademicClass` for that subject exists in one of `decision.campus_codes`. Class-level filters still re-apply campus scope.
- `GET /api/academic/training-scope`: backend returns the effective campus codes plus branch mapping from `AcademicCampus`, including preferred branch/campus for scoped operators.
- `frontend/components/layout/AppShell.tsx`: Training Operations routes normalize the URL to an allowed branch/campus; a branch change drops stale branch-specific `term_id` and `block_id`. User role display now uses the highest active business assignment and shows a scoped campus owner as `Chủ cơ sở · <CAMPUS>`.
- `frontend/hooks/useAcademicTableState.ts`: branch/campus updates are constrained by the backend training scope and now expose `scopeReady` only after the scope request completes for an authenticated user.
- `frontend/app/student-management/StudentManagementPlatformPage.tsx` and subject class page: term/campus/subject/class requests are gated on `scopeReady`; filters/actions are disabled during scope resolution and tables stay in loading state. This prevents the initial generic Poly request from racing the PTCĐ/TK correction.

### Git commits already present from the timed-out assistant turn
- `fb0bac28c54e3cf5477d86d214716cfc30927623` — allow campus owners to open subjects in assigned campus.
- `33e42293ec9bb8a5b8b5ea4edb470704729803ae` — expose Training Operations campus scope.
- `f9735a47d2297cc9515e00f43e427c702e20103b` — register training-scope API route.
- `2f10dc569851e844bb7f3da0e7b2dc3afd805af1` — align training defaults and business-role label.
- `dd92cc18f8b076b54511a66c3c8ac1ea2861f5ea` — initial regression contract.
- `cbf603e63a6fc0163b9d3893b0d04b7b74fe584c` — enforce scoped branch/campus in academic table state.
- `7fad4c545a6ba43196001d35c1dc8c0b14835174` — guard scoped academic filter state.

### Additional hardening after resuming the timed-out chat
- `869c90500638cc18ca586f992e151a56d2fc31ad` — expose `scopeReady` from the shared academic table state.
- `9c9f854c3016c2f60f28cc5b09fc36ea8cb4c4c4` — gate subject-class requests on resolved training scope.
- `270aacd41b5c66d04870564de6efc2234bc479df` — gate Student Management term/campus/subject/job requests on resolved training scope.
- `105e3026cce5a2a6239f76c2704730469d4c6c15` — static regression assertions for the scope-ready gate.

### Verification boundaries
- GitHub branch and source files were re-read after the writes and show the expected scope-ready guards.
- The repository has no required branch status checks for this branch and no new CI result was observed for these commits during this chat.
- No production deployment was performed from ChatGPT. The 403 screenshot/request happened before these new commits and cannot be used to judge the patched source.

## Addendum 2026-09-11 — branch RBAC, report/jobs, platform import, replica reads

- Branch ownership is explicit: `CAMPUS_OWNER` with `scope_type=BRANCH, scope_id=poly` owns all Poly campuses; `scope_id=ptcd` owns all PTCĐ campuses; only a `SYSTEM` assignment spans both. Legacy `CAMPUS/*` assignments are fail-closed and must be re-granted explicitly. `BusinessRBACService.accessible_branch_codes()` and `accessible_campus_branch_pairs()` preserve duplicate campus codes that exist in both systems.
- Student Operations class, subject, identity, overview and teacher-report filters enforce `(branch, campus)` pairs. A PTCĐ owner cannot access a Poly class that happens to use the same campus code. Training scope and term/block/campus catalog routes reject a foreign branch or an omitted scope that would widen access.
- Open edX course mapping is strict: PTCĐ maps only Org `FPS`; Poly maps only Org `FPL`. Existing mappings with the opposite Org are displayed as `invalid_org_match`, excluded from effective/direct/inherited/fast-path readers, and never silently overwritten or reused.
- `teacher_report.async` no longer selects the unused `UdemyStudentProgress` entity and no longer passes too many positional arguments to `Query.outerjoin()`.
- `/jobs` renders five primary job sources first; quiz-instance history and analytics status load independently in the background. A generation token discards stale supplemental results after refresh/filter changes.
- `/subject-management` supports an Excel plan with exactly `Mã môn | Nền tảng`. The selected term and branch come from the screen. Preview matches the full database catalog, reports missing/duplicate/invalid rows, stores the importer and a short-lived preview token, and requires explicit Apply. Platforms are `CMS`, `Udemy`, `Khác (Other)` or unassigned. Migration `0063_subject_platform_other` updates the database check constraint.
- CMS-FPT connector learning/progress/grade report helpers run inside `replica_reads` and use the configured `read_replica` alias. The router fails closed when the alias is absent, points at primary, or a nested dependency attempts a primary read. Enrollment/publish/write paths remain on `default`. Tutor plugin settings wire the alias and connector router for LMS and CMS.

### Verification 2026-09-11

- CMS-AI backend targeted regressions: 37 passed (branch boundary, mapping, subject platform import, teacher report outerjoin contract).
- CMS-AI backend compileall: passed.
- CMS-AI frontend `npm run typecheck`: passed.
- CMS-FPT compileall, replica validator and connector unittest: passed (12 tests).
- Browser E2E execution was not run because the managed environment did not expose a Chromium executable; E2E specs remain in source.

### Deployment notes

- CMS-AI: build and roll out the `ai-server-backend` image and run Alembic migration `0063_subject_platform_other`; rebuild/redeploy the frontend for the Jobs, user-RBAC and subject-management UI changes.
- CMS-FPT: rebuild LMS and CMS images from `fpt-indigo-ui`; ensure `MYSQL_REPLICA_HOST`, `MYSQL_REPLICA_PORT`, and replica credentials point to the read-only MySQL replica. Do not set `AI_CONNECTOR_READ_DB_ALIAS=default`. Verify connector report endpoints return a structured 503 if replica connectivity is unavailable.

### Local handoff commits

- CMS-AI local commit: `9d457e4` (`feat: split training scopes and optimize reports`).
- CMS-FPT local commit: `d504eee` (`fix: route connector reports to read replica`).
- Push was attempted for both canonical branches but rejected by the automatic review after the session usage limit was reached; run the push commands when GitHub access is available.

## Addendum 2026-09-11 — Excel teacher-report export latency

- The export worker's 12–62% stage is the live CMS/Open edX grade refresh, performed per mapped class before workbook generation. It is not Excel serialization.
- Repeated `export_excel` jobs now reuse a complete, non-preserved CMS snapshot for up to `ACADEMIC_TEACHER_REPORT_EXPORT_SNAPSHOT_MAX_AGE_SECONDS` (default 300 seconds). Missing, incomplete, old, or `grade_preserved` snapshots still force the live connector and fail closed on errors. `rebuild_cache` remains forced-live.
- Read-only class analytics batches now allow up to 500 compact students per connector request (enrollment/account creation stays at 100). Old `teacher-reports/` object cleanup moved to the periodic artifact-cleanup task so object-storage listing is not on the export critical path.
- Workbook guide metadata records how many classes used the bounded snapshot window and how many were refreshed live.
- Background Excel jobs now use openpyxl `write_only` workbooks; the direct small-export compatibility path remains normal mode. This keeps large exports (around 50,000 grade records) from retaining the full workbook in worker RAM.

### Verification

- Teacher-report freshness/worker reliability regressions: 19 passed.
- Backend `compileall`: passed.
- Streaming workbook smoke test with populated overview/class/student rows: passed.

## Addendum 2026-09-11 — email-first RBAC identities, Dash last login, daily score refresh

- Interactive RBAC grants are email-first. The backend normalizes the email, derives the CMS username from the local part before `@`, and ignores a mismatching client-supplied `user_id`. The UI shows the derived username as a preview and no longer asks operators to type it separately.
- Granting a permission calls the Open edX Connector `users/resolve` endpoint with `create_missing=true` and a staff payload. The connector creates/repairs the Django `UserProfile` and enforces `set_unusable_password()` for newly created users; no password is generated or returned. Provisioning failure is fail-closed before the AI RBAC assignment is committed. Legacy Excel/bootstrap rows may still carry `user_id`, but new API grants require email.
- Dash stores identity records in `ai_user_profiles` (`backend/app/models/identity.py`) with `last_login_at`. The successful CMS session exchange upserts this record. RBAC list/effective/scope responses enrich assignments with one batch lookup, and `/users` renders username once followed by email and “Đăng nhập lần cuối”. Migration `0064_rbac_identity_login` creates the table/indexes.
- Celery beat timezone is `Asia/Ho_Chi_Minh`. `academic_sync_all_student_scores_task` runs daily at `05:00`, fans out durable `learning_sync` jobs for every active class, reuses active jobs, and processes class rosters with the configured 1,000–20,000 ceiling. The existing connector learning path remains read-only and uses CMS-FPT `read_replica` for score/progress reads.

### Verification

- New RBAC identity/login/scheduler contract: 7 passed.
- Backend compileall and frontend `npm run typecheck`: passed.
- Existing campus-owner contract retains the deliberate fail-closed behavior for legacy `CAMPUS/*` wildcard assignments.

### Deployment notes

- CMS-AI: run Alembic migration `0064_rbac_identity_login`, then rebuild/roll out backend and frontend. Verify `/api/rbac/assignments` contains `last_login_at` and beat logs show `academic-score-sync-all-students` at 05:00 Asia/Ho_Chi_Minh.
- CMS-FPT: rebuild LMS/CMS images from `fpt-indigo-ui` so the connector account-provisioning/profile/no-password change is deployed. Keep `AI_CONNECTOR_READ_DB_ALIAS=read_replica` and replica credentials configured.

## 2026-09-11 — Udemy teacher detail 500 regression
- Root cause for `GET /api/academic/training/teachers?...learning_platform=udemy&teacher_id=...&include_classes=true`: the Udemy branch never initialized the CMS-only local `learning`, but the common class payload later read `learning.get('learning_component_summaries')`. This raises `UnboundLocalError` and returns HTTP 500 for Udemy teacher drill-down.
- Fixed by initializing `learning: dict[str, Any] = {}` before the Udemy/CMS platform branch. CMS behavior remains unchanged; Udemy returns an empty `learning_component_summaries`.
- Regression coverage: `backend/app/tests/test_teacher_report_udemy_learning_local_contract.py` and existing outerjoin contract.

## 2026-09-11 — Udemy plan date locale regression
- Fixed generated Udemy plan template so Week deadline cells are explicit `dd/mm/yyyy` text (`@`) instead of locale-sensitive Excel date cells.
- `03/10/2026` therefore remains 3 October 2026 even on workstations using an MM/DD locale.
- Backend parser remains backward-compatible with real Excel date cells, serial values, `dd/mm/yyyy`, and ISO dates.
- Regression test added at `backend/app/tests/test_udemy_plan_date_locale_regression.py`; targeted local suite was verified before the GitHub source patch.

## 2026-09-11 — Udemy to CMS AP reconciliation and audit aggregation

- Verified branch source fix commit: `689d871a766404f02425cc14522117d9f763fd09`.
- Switching a subject delivery from `udemy` to `cms` now preserves platform history and sets `metadata_json.ap_reconcile_required=true` with reason `learning_platform_changed_udemy_to_cms`.
- The AP Celery worker now uses `app.services.academic.ap_importer.AcademicImportService`, so a subsequent AP import reconciles AP-owned class teacher/student links instead of only upserting.
- The reconcile marker is cleared only after a non-dry-run AP sync finishes with `status=completed` and `counters.errors == 0`. Partial/error/dry-run syncs do not clear it.
- Per-class success audit rows are kept for manual class operations, but bulk/scheduled child success rows are suppressed. Failure audit rows remain per child.
- The daily 05:00 Asia/Ho_Chi_Minh score scheduler writes one summary audit action `academic.sync_all_student_scores` with success/failed status.
- Regression files: `backend/app/tests/test_ap_platform_resync_and_class_audit_regression.py` and `backend/app/tests/test_ap_platform_resync_integration.py`.
- GitHub Actions RED→GREEN verification run `34604486553` completed successfully: RED reproduced before patch, GREEN passed after patch, and `py_compile` passed for changed production modules.
- This verifies source/tests only. Kubernetes deployment and production runtime verification have not been performed in this change.

