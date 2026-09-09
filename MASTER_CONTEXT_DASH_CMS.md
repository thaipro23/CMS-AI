# MASTER CONTEXT — DASH CMS

Updated: 2026-09-09 (Asia/Bangkok / UTC+7)

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

CURRENT TASK: Fix PTCĐ `/get-data-cms` campus field and remove `/premises` API campus refresh button.

STATUS: SOURCE UPDATED / STATIC REGRESSION PASS / NOT DEPLOYED.

FILES MODIFIED:

- `backend/app/services/ap_academic_sync.py`
- `frontend/app/premises/layout.tsx`
- `frontend/styles/fa26-layout-hotfix.css`
- `frontend/app/ap-sync/page.tsx`
- `backend/app/tests/test_ap_sync_manual_campus_contract.py`
- `MASTER_CONTEXT_DASH_CMS.md`

NEXT ACTION:

1. Build/deploy a new Dash CMS image containing this working copy.
2. Verify runtime image for backend + worker + frontend.
3. Test a single `/get-data-cms` request with `campus_code` and confirm HTTP 200.
4. Run PTCĐ sync again with the same 18 Dash campuses.
5. Verify classes/students/teachers/subjects are imported.
6. Separately decide whether to change all-error runs from `completed` to failed/partial.

## Production claim

- Source updated: YES.
- Tests: partial; bounded static regression PASS.
- Commit: NOT VERIFIED (ZIP has no `.git`).
- Push: NOT VERIFIED.
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
