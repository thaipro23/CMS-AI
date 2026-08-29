# Bank module — UX audit, design contract and implementation plan

**Baseline:** `v25.9.16.7.2.64.16.5.7.2.3 — Frontend Visual Ergonomics & Navigation Hotfix`  
**Batch implemented:** AppShell foundation + `/bank/departments`  
**Scope rule:** preserve routes, API contracts, RBAC, workflow semantics, server-side data contracts and Open edX integration.

## 1. Product and workflow map

```text
Department / Bộ môn
  → Subject / Môn học
    → SubjectOffering / Phiên bản môn theo học kỳ
      → Chapter / Bài học
        → Material versions / Tài liệu
        → Question generation job
        → Questions: pending_review → approved | rejected | draft_error
        → Document diff and carry-over review
        → Release readiness
        → Frozen Release snapshot
          → Publish to Open edX Library
          → Map course and chapter scope
          → Create Quiz / Final test on CMS
          → Audit, history and safe rollback
```

Release and Quiz are downstream outputs. They are not additional hierarchy levels and must never be presented as children of Chapter.

## 2. Route, job-to-be-done and risk inventory

| Route | Primary user job | Main data | Primary action | High-risk actions |
|---|---|---|---|---|
| `/bank` | Understand workload and decide the next operational task | KPI, alerts, trends, activity | Open the most urgent workflow | None; drill-down must preserve filter context |
| `/bank/departments` | Find and maintain the top-level ownership scope | Departments and aggregate counts | Add department or open its subjects | Delete department; incorrect permission exposure |
| `/bank/departments/{departmentId}/subjects` | Find a subject in a department and maintain ownership metadata | Subjects and review/question totals | Add subject or open versions | Delete subject; assign/update outside scope |
| `/bank/subjects/{subjectId}/versions` | Open or create the final subject version for a term | Subject offerings, term, readiness totals | Create/clone subject version | Clone wrong term/source; delete version with descendants |
| `/bank/subject-versions/{versionId}/chapters` | Manage the ordered lesson structure | Chapters and question/review totals | Add chapter or open workspace | Delete/reorder the wrong chapter |
| `/bank/chapters/{chapterId}` | Author, review and prepare a bank for release | Materials, bank version, questions, diff, release readiness | Contextual next action | Generate cost, reject/bulk review, retire, release creation, publish |
| `/bank/search` | Find a question or entity across a large bank | Search results | Open result | Stale/incomplete indexing feedback |
| `/bank/quiz` | Guided mapping and creation on Open edX CMS | Course mapping, release, chapter mappings, quiz configuration | Map course, then create | Creating against wrong course/section; duplicate job |
| `/bank/history` | Audit releases/quizzes and recover safely | Releases, quiz instances, operation status | Inspect record | Rollback; destructive release deletion where allowed |

## 3. Data, API and URL-state contract

The backend already provides a broad Bank API under `/api/question-bank-v2`, including:

- hierarchy summary and paginated endpoints for departments, subjects, subject offerings and chapters;
- material upload/extraction jobs;
- question page, cursor feed, import/export and bulk review;
- document diff preview/persist/carry-over/retire;
- release readiness, snapshot preview, publish and publish audit;
- course mapping, quiz auto-map, create jobs and rollback;
- operation jobs, dashboard analytics, alerts and search.

### URL state

List and question-table state must remain shareable and restorable through URL parameters. The current `useUrlTableState` contract is retained for search, status, sort, page, page size, density and visible columns. A refresh, browser Back or copied URL must not reset the operator's working view.

### Scale constraint

The target scale includes roughly 1.5 million questions. Question queries, search, filters, sort, export and bulk operations must stay server-side. Department is low-cardinality, so the existing summary endpoint can support Batch 1 without changing the API. Subject/version/chapter pages should migrate to paginated endpoints when their current summary payload becomes a measurable bottleneck; the UI must not conceal that backend contract gap by fetching all records.

## 4. Roles and capability boundaries

Canonical roles include `SYSTEM_ADMIN`, `DEPARTMENT_HEAD`, `SUBJECT_OWNER` and `QUESTION_REVIEWER`. The frontend may hide unavailable actions, but backend authorization remains authoritative.

Relevant Bank capabilities include:

```text
bank.view
subject.create
subject.update
document.manage
question.generate
question.edit
question.approve
question.reject
bank.release.create
bank.release.publish
quiz.preview
quiz.create_openedx
audit.view
```

Batch 1 uses exact capability checks rather than broad legacy role assumptions:

- create department: `department.manage_all`;
- edit/delete a department: scoped `department.update` on that department;
- view route: existing `view_questions` bridge / Bank permission contract.

## 5. UX audit

### 5.1 Information architecture and navigation

| Problem | User impact | Root cause | Treatment |
|---|---|---|---|
| `/bank` prefix matching marked both **Tổng quan** and **Ngân hàng đề** active on hierarchy routes. | Users could not reliably tell where they were; the wrong group looked current. | Navigation used loose `startsWith('/bank')` matching. | Introduce scored, explicit route matching; `/bank` is exact, hierarchy prefixes map to one Bank item. |
| Sidebar behavior and CSS breakpoint were inconsistent. | At tablet widths the shell could appear collapsed rather than becoming a usable drawer. | JS breakpoint was 767px while layout requirements and CSS behavior extended higher. | Standardize mobile shell behavior at `max-width: 1023px`; use a modal navigation drawer. |
| Desktop sidebar defaulted to collapsed for users without a preference. | New users had to infer unlabeled icons and spent more time learning the product. | Compactness was prioritized over discoverability. | Default to expanded; preserve an explicit saved preference only. |
| Page title, eyebrow and breadcrumb could duplicate the same label. | Repetitive chrome consumed vertical space and weakened hierarchy. | Page-level components registered overlapping information. | Topbar is the single title/context surface; normalize the terminal breadcrumb when it equals the page title. |
| Hierarchy pages are visually similar but implemented independently. | Small inconsistencies accumulate between Department, Subject, Version and Chapter. | Repeated local toolbar/header markup. | Standardize `SectionHeader`, `FilterToolbar`, `EnterpriseDataTable`, status and dialogs before migrating the remaining pages. |

### 5.2 Action hierarchy

| Problem | User impact | Root cause | Treatment |
|---|---|---|---|
| Create, refresh, filter and row actions did not consistently express priority. | Operators scanned every control instead of finding the next action immediately. | Pages assembled buttons ad hoc. | One page/section primary action, secondary refresh/filter actions, direct row actions and separate destructive confirmation. |
| Single actions were sometimes placed in generic menus on related pages. | Adds a click and lowers discoverability. | Generic table action pattern used without evaluating action count. | A single meaningful action stays visible; overflow menus are only for multiple low-frequency actions. |
| Disabled and destructive states lacked consistent consequences. | Increased risk of wrong deletion or confusion about unavailable operations. | Confirmation and messaging were local implementations. | Shared accessible dialog footer, consequence statement and server error feedback. |
| Chapter commands compete as near-equal buttons. | Users cannot tell whether to attach documents, generate, review, release or publish next. | Workflow stages are represented as a flat command strip. | Batch 5 will introduce a stage-aware workspace with one recommended next action and subordinate tools. |

### 5.3 Data tables and density

| Problem | User impact | Root cause | Treatment |
|---|---|---|---|
| Hierarchy pages used similar tables but inconsistent controls, status labels and empty/error behavior. | Users relearn each list and may mistake an API failure for no records. | Local filtering and `catch(() => null)` patterns. | Batch 1 adds explicit loading/error/retry, result count, standard status, density, column visibility and page-size controls. |
| Several summary pages load all rows and paginate in the browser. | Latency and memory use grow with the catalog; URL page state may not correspond to a server query. | Convenience summary endpoints were treated as scalable list endpoints. | Preserve Batch 1 API; schedule controlled migration of larger hierarchy lists to paginated endpoints. |
| Identity columns can lose useful width while secondary columns compete equally. | Names/codes wrap excessively and scanning slows down. | Fixed-width table definitions without a clear identity hierarchy. | Identity column receives the largest flexible width; STT remains first and actions last/sticky. |
| A failed fetch was converted into an empty table. | Operators can make decisions based on false “no data.” | Error was swallowed. | Separate loading, error, permission and empty states; retry does not reset URL filters. |

### 5.4 Feedback, safety and accessibility

| Problem | User impact | Root cause | Treatment |
|---|---|---|---|
| Operation feedback was not consistently typed as success/error. | A failed action could look visually similar to confirmation. | `useAsyncMessage` exposed only free text. | Add a backwards-compatible message tone and render `InlineNotice`. |
| Dialog action placement varied. | Keyboard and screen-reader behavior was less predictable. | Dialog footer was reimplemented inside form content. | Extend the shared modal wrapper to use `AccessibleDialog` footer, busy state and description. |
| Focus return and Escape behavior depended on each caller. | Keyboard users could lose their position. | Local modal structures. | Keep shared focus trap, initial focus, Escape and focus-return contract. |
| Destructive copy was generic. | The user may not understand the cascade or irreversibility. | Confirmation focused on “Are you sure?” rather than consequence. | Explain that deletion is blocked or may affect descendants according to backend validation; show exact entity identity. |

### 5.5 Responsive and visual ergonomics

| Problem | User impact | Root cause | Treatment |
|---|---|---|---|
| Shell state could create body-level horizontal/vertical scrolling. | Sticky chrome became unreliable and tables could move the whole page. | Multiple legacy CSS layers override shell dimensions. | Lock body/app shell to viewport; sidebar/topbar remain fixed in the shell and only main content scrolls vertically. |
| Dense toolbars can overflow at 1024–768px. | Actions become clipped or force horizontal page scroll. | Fixed field widths and no intentional wrapping order. | Filter fields wrap first; primary action remains visible; result count and secondary controls move to a second line. |
| Mobile table usage lacked a single documented strategy. | Important fields may disappear or the whole page may scroll sideways. | Breakpoint-specific hiding was used inconsistently. | Keep identity/status/actions visible; allow only table container horizontal scroll when necessary; no body horizontal scroll. |
| Typography had historical heavy-weight overrides. | Long question/table content became tiring to read. | Layered visual hotfixes and excessive font weights. | Continue 400–500 body, 600 important labels/actions, avoid heavy full-paragraph text. |

### 5.6 Maintainability audit

1. `frontend/styles/globals.css` is approximately 8,700 lines and is supplemented by multiple override files. Cascade order is acting as an implicit design system, which increases regression risk.
2. `ChapterWorkspacePage.tsx` is a very large orchestration component, combining data loading, workflow rules, dialogs, table actions and presentation.
3. Hierarchy list pages duplicate filtering, create/edit/delete dialog and table configuration logic.
4. Status presentation exists in both local `bank-row-status` logic and shared `StatusBadge`.
5. Some pages use summary endpoints with local pagination while the system also has paginated endpoints, creating two data-access patterns.
6. Error handling is inconsistent; silent catches are the highest-priority correctness issue because they produce false empty states.

Cleanup should be incremental. Do not rewrite the entire frontend or delete legacy CSS before route-level visual regression coverage exists.

## 6. Bank design contract

### 6.1 App shell

- Dark, expanded desktop sidebar; width 240px, user-collapsible to 72px.
- Light workspace and a 60px topbar.
- Sidebar and topbar stay inside a viewport-locked shell.
- Only `.enterprise-content` scrolls vertically.
- Body and workspace never scroll horizontally.
- At 1023px and below, sidebar becomes an accessible drawer with overlay, Escape close and focus return.
- Exactly one navigation item is active.
- Page title/context appears only in topbar.

### 6.2 Page and section structure

```text
Topbar: hierarchy context + page title + global/user status
Main content:
  optional operation notice
  one bounded section
    SectionHeader: purpose + result context + primary action
    FilterToolbar: search/filter/result count/supporting actions
    EnterpriseDataTable or workflow content
```

Avoid a full-screen-height card merely to contain a short table.

### 6.3 Spacing and typography

- Spacing scale: `4 / 8 / 12 / 16 / 20 / 24 / 32`.
- Workspace horizontal padding: 22px desktop, 16px compact desktop/tablet, 12–14px mobile.
- Body/table content: 400–500.
- Labels, section titles, important buttons and statuses: 600.
- No 800/900 weight for paragraphs, questions, answers or entire table cells.
- Section surface radius: 12px; borders are structural rather than decorative.

### 6.4 Action hierarchy

- **Primary:** one workflow-driving action per section.
- **Secondary:** refresh, export, inspect, configure.
- **Tertiary:** low-frequency non-destructive actions.
- **Destructive:** explicit red treatment and consequence confirmation.
- One or two row actions are direct; an overflow menu is permitted only when there are multiple secondary actions.
- Disabled controls expose a reason in adjacent help text or accessible description.

### 6.5 Filter toolbar

- Search occupies the most flexible width.
- Filters have visible labels; placeholder text does not replace labels.
- Result count reflects the current filter.
- Filter changes reset page to 1 but preserve other URL state.
- Refresh is secondary and never clears filters.
- At smaller widths, fields wrap in an intentional order and remain at least 44px high for touch use.

### 6.6 Enterprise table

- STT first; action last and sticky when needed.
- Identity column is flexible and receives most width.
- Long identity/description text wraps; critical content is not silently truncated.
- Server-side search/filter/sort/pagination for large datasets.
- URL state for page, page size, sort, filters, density and visible columns.
- Page sizes: 10, 20, 50, 100.
- Explicit loading, empty, error and permission states.
- Only the table scroll container may scroll horizontally.
- Density and column visibility are user controls, not breakpoint-driven data loss.

### 6.7 Status badge

Status vocabulary is semantic and reusable:

- active / ready / approved / published: positive;
- pending review / needs attention / processing: warning or information;
- rejected / failed / blocked / rolled back: danger;
- inactive / draft / empty: neutral.

Do not encode status meaning by color alone; text is mandatory.

### 6.8 Dialog, drawer and confirmation

- Create/edit/review forms use centered accessible dialogs.
- Read-only lightweight detail may use a drawer in later batches.
- Dialog has label, description, focus trap, initial focus, Escape, focus return and busy state.
- Footer is sticky inside the dialog layout, never overlays the form and never causes horizontal scroll.
- Destructive confirmation names the record and describes impact.
- No native `alert()` or `confirm()`.

### 6.9 Loading, empty, error and permission

- Loading uses skeleton/table state without shifting the page shell.
- Empty state explains whether no data exists or no data matches filters.
- Error state includes a retry action and retains URL/table state.
- Permission state says the user lacks access; it must not resemble “no records.”
- Background jobs show queued/running/success/failure and survive page refresh through job polling.

### 6.10 Responsive acceptance

- **1440 / 1366:** expanded fixed sidebar, dense table, single-line toolbar where possible.
- **1024:** compact desktop shell; toolbar may wrap; no body overflow.
- **768:** navigation drawer; primary action remains visible; table container owns horizontal overflow.
- **390:** stacked section header and filters; full-width main actions; touch targets at least 44px; dialog width bounded to viewport.

## 7. Implementation plan

| Batch | Scope | Main risk controlled | Independent acceptance |
|---|---|---|---|
| 1 | Foundation tokens, AppShell, shared section/filter primitives, `/bank/departments` | Navigation ambiguity, false empty state, shell overflow | Typecheck/lint/build; mocked browser route at 1440/1366/1024/768/390 |
| 2 | Subject, Subject Version and Chapter list pages | Pattern drift and client-side list scaling | Same table/action contract; scoped RBAC; URL-state regression |
| 3 | Shared hierarchy data adapter and paginated endpoint adoption where required | Loading all catalog rows | Server query evidence; Back/F5/share-link behavior |
| 4 | Bank dashboard and global search | Decision overload and lost filter context | KPI/drill-down accuracy, cache/error states |
| 5 | Chapter authoring workspace information hierarchy | Flat commands and unclear next action | Materials/quota/review/release states with role data |
| 6 | Generate, document and import dialogs | Cost ambiguity and unsafe files | Cost/source/limit/job messaging; validation states |
| 7 | Review workbench | Reviewer throughput and content competition | Keyboard + pointer flow; evidence; edit/reject/approve |
| 8 | Diff, readiness, Release snapshot and publish | Confusing live data vs frozen release | Snapshot provenance, irreversible-state copy, audit |
| 9 | Guided Quiz creation and History | Wrong course mapping and duplicate creation | Step gating, job idempotency feedback, safe rollback |
| 10 | Cross-route responsive/a11y and staged CSS cleanup | Cascade regressions | Browser matrix, focus/overflow checks, delete dead CSS only with coverage |

## 8. Batch 1 implementation decisions

### AppShell

- Added explicit route matching and longest-match scoring so only one sidebar entry is active.
- Made `/bank` exact and mapped hierarchy routes to **Ngân hàng đề**.
- Defaulted desktop sidebar to expanded when no preference exists.
- Unified the drawer breakpoint at 1023px.
- Normalized topbar breadcrumbs to avoid repeating the page title.
- Added a final, isolated Bank redesign stylesheet rather than modifying broad legacy layers in the first batch.

### `/bank/departments`

- Replaced copied/unused imports with a focused page implementation.
- Added explicit loading, API error, retry and filtered-empty states.
- Preserved URL-driven table search, status, page, page size, density and visible columns.
- Added a clear section header with a single primary **Thêm bộ môn** action.
- Standardized search/status/result count/refresh in a reusable filter toolbar.
- Kept identity information dominant and row edit/delete actions direct.
- Enforced exact create/update permission checks in the UI.
- Added accessible create/edit dialog and consequence-based delete confirmation.
- Added typed success/error operation notices.
- Kept real API data; no KPI or record mock is included in production source.

## 9. Batch 1 acceptance checklist

- [x] Routes and backend contracts unchanged.
- [x] No change to release, review, publish, quiz or Open edX semantics.
- [x] AppShell has exactly one active Bank navigation item.
- [x] Sidebar expands by default and converts to drawer at tablet/mobile width.
- [x] Main content owns vertical scrolling; body has no horizontal scrolling by design.
- [x] Department table keeps STT first and actions last.
- [x] URL state, density, column visibility and page sizes 10/20/50/100 retained.
- [x] Loading, error/retry and empty states separated.
- [x] Create/edit/delete respects capability and scoped capability checks.
- [x] Native alert/confirm not introduced.
- [ ] Real UAT data, SSO cookie and all production roles require deployment-time verification.
- [ ] Large-catalog latency requires production-like data volume; mocked browser evidence only validates UI behavior.
