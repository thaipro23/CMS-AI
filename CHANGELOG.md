## v25.9.15.6.34 - Dashboard Summary Engine

- Added `ai_bank_chapter_stats` summary table and SQLAlchemy model `BankChapterStats`.
- Added `BankDashboardStatsService` so Bank Dashboard reads per-chapter summary rows plus small hierarchy tables instead of aggregating `ai_questions` at request time.
- Added admin endpoints `GET /api/question-bank-v2/admin/stats/health` and `POST /api/question-bank-v2/admin/stats/rebuild[?chapter_id=...]`.
- Added Redis cache for dashboard overview and hierarchy summaries with `BANK_DASHBOARD_CACHE_TTL_SECONDS` defaulting to 45 seconds.
- Added best-effort stats refresh after material, question review/generate, release and chapter/bank-version mutations.
- Kept full search engine work for the next planned `.35`; interim dashboard search does not touch `ai_questions`.

## v25.9.15.6.33 - Pagination Contract toàn hệ thống Bank

- Changed Bank Manager list APIs from unbounded arrays to explicit `items/total/page/page_size/total_pages/has_next` contracts.
- Added cursor/keyset pagination for `GET /question-bank-v2/bank-versions/{bank_version_id}/questions` using `(created_at, id)` instead of deep offset.
- Added Pydantic generic schemas `PaginatedOut[T]` and `CursorPaginatedOut[T]`.
- Removed direct `.all()` list returns from `backend/app/api/routes/question_bank_v2.py`; list reads now pass through pagination helpers.
- Kept frontend compatibility by unwrapping paginated backend responses in `frontend/lib/api.ts`, so existing screens still receive arrays until the later frontend scale redesign.
- Added no-op Alembic marker `0016_v25_9_15_6_33_pagination_contract.py` for deployment-order verification.

## v25.9.15.6.32 - Database Scale Foundation

- Added PostgreSQL-safe composite indexes required before scaling Bank Manager to 6 departments, 300 subjects, 1,500 subject versions, 15,000 chapters and 1,500,000 questions.
- New migration `0015_v25_9_15_6_32_database_scale_foundation.py` uses `CREATE INDEX CONCURRENTLY IF NOT EXISTS` on PostgreSQL and normal idempotent indexes in dev/test databases.
- Added hot-path indexes for `ai_questions`, `ai_question_bank_versions`, `ai_question_bank_releases`, `ai_bank_release_questions`, and `ai_material_chunks`.
- Added safe extra indexes for subject offerings, chapters, quiz history and audit drill-down.
- Added DB pool settings: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_STATEMENT_TIMEOUT_MS`.
- Runtime SQLAlchemy engine now applies PostgreSQL pool sizing and per-connection `statement_timeout`.
- Production backend now runs Gunicorn + UvicornWorker with `WEB_CONCURRENCY` instead of a single Uvicorn worker.
- Added `GET /api/health/db` to verify database reachability and pool settings after deploy.
- This version intentionally does not change pagination/dashboard contracts; those remain the next planned versions.

## v25.9.15.6.31.13 - Bank Business RBAC Roles

- Thêm RBAC nghiệp vụ Bank-first theo đúng kế hoạch: SYSTEM_ADMIN, DEPARTMENT_HEAD, SUBJECT_OWNER, QUESTION_REVIEWER.
- Thêm bảng `ai_rbac_roles`, `ai_rbac_permissions`, `ai_rbac_role_permissions`, `ai_user_role_assignments`.
- Gán quyền theo scope SYSTEM / DEPARTMENT / SUBJECT / SUBJECT_VERSION / CHAPTER / COURSE.
- Bậc trên kế thừa quyền bậc dưới nhưng chỉ trong scope cha: Trưởng bộ môn chỉ trong bộ môn, Chủ môn chỉ trong môn/phiên bản, Người duyệt chỉ trong môn/chapter được giao.
- Thêm API `/api/rbac/me`, `/api/rbac/roles`, `/api/rbac/permissions`, `/api/rbac/assignments`, `/api/rbac/bootstrap/system-admin`.
- `/auth/openedx-session/exchange` nâng legacy role theo assignment AI Server sau khi user đăng nhập CMS, nhưng vẫn không tin `is_staff` Open edX là AI admin.
- Bank Manager kiểm tra business permission cho bộ môn/môn/version/chapter/bank/release/quiz thay vì chỉ dựa vào legacy role.
- Trang `/users` có tab quản lý assignment: Admin gán Trưởng bộ môn, Trưởng bộ môn gán Chủ môn, Chủ môn gán Người duyệt.


## v25.9.15.6.31.8 - Bank Hierarchy Inline Section Headers

- Bỏ page header lớn ở các trang phân cấp Ngân hàng đề.
- Đưa tiêu đề/mô tả vào section-head của card chính để màn hình gọn hơn.
- Các trang được chỉnh: departments, subjects, versions, chapters, chapter workspace, history.
- Không sửa backend, không cần migrate DB.


## v25.9.15.6.31.7 - Merge Dashboard into Bank + Chart Overview

- Gộp `/dashboard` vào `/bank`; `/dashboard` redirect về `/bank`.
- Sidebar bỏ mục Tổng quan vận hành để tránh trùng Dashboard Bank.
- `/bank` thêm biểu đồ tổng quan theo luồng Bank/Quiz-first: tình trạng câu hỏi, quy mô ngân hàng, Quiz Open edX, job generate.
- `/bank` giữ tìm nhanh, việc cần làm và nhật ký gần đây để giáo viên/quản trị xem một màn hình là đủ.


## v25.9.15.6.31.5 - Chapter Action Buttons + System Font Polish

- Make chapter workspace action buttons more visible and easier to scan.
- Add button-specific affordances for material, generate, review, diff and published states.
- Reset question-card typography to system font stack; remove aggressive letter spacing / heavy font rendering.
- Frontend-only release; no migration required.


## v25.9.15.6.31.4 - Bank hierarchy polish + stronger actions + question typography

- Removed redundant Bank flow tabs from Department/Subject/Version/Chapter pages because breadcrumbs already carry the hierarchy.
- Made buttons more visible and action-oriented across Bank workspace, filters and popups.
- Refined question card typography, spacing and answer option readability.
- Kept operations/admin sidebar labels aligned with the new Bank workflow.


## v25.9.15.6.31 - Cohesive Bank Hierarchy + Chapter Workspace UX

- Làm đồng bộ bố cục các trang Bank hierarchy: Departments, Subjects, Subject Versions, Chapters và Chapter Workspace.
- Thêm flow tabs để giáo viên biết đang ở bước nào trong luồng Bộ môn → Môn → Version → Bài → Câu hỏi → Release.
- Chuyển khối Tài liệu và Tạo câu hỏi từ tài liệu trong chapter workspace thành popup mở bằng nút.
- Thêm filter câu hỏi theo trạng thái, độ khó và sắp xếp theo ưu tiên xử lý/độ khó/chất lượng.
- Bổ sung CSS hiện đại hơn cho card/list, command bar, filter bar và popup workspace.


## v25.9.15.6.28 - Bank Quiz Clean Workbench UX

- Cleaned `/bank/quiz` to reduce scrolling and visual noise.
- Course ID now triggers auto map preview after input; removed the manual auto-find button.
- Moved `Lưu cấu hình` and `Tạo Quiz` actions to the top of the sticky settings panel.
- Quiz history is filtered by the current Course ID only.
- Simplified result copy and renamed mapping to configuration.
- Switched the main workspace background to white while keeping FPT orange accents.


## v25.9.15.6.26 - Bank Quiz UX + Sidebar Polish

- Reworked `/bank/quiz` into a two-column workbench with a sticky settings panel for Course ID, version, difficulty, and timer configuration.
- Added summary cards and kept create actions accessible without scrolling back to the top.
- Added missing global CSS for `.alert`, `.card-soft`, `.toggle-line`, `.option-grid`, and quiz workbench states.
- Grouped sidebar navigation and added icons for faster scanning.


## v25.9.15.6.25 - Force Save Quiz Timer Config After Quiz Create

- AI Server force-save timer config into LMS `openedx_unit_reset` after Quiz node creation, using real sequence/unit usage keys returned by Open edX.
- Added `OpenEdXConnector.upsert_quiz_timer_config` and real LMS HMAC call to `/api/unit-reset/v1/quiz-config/upsert`.
- `openedx_unit_reset` timer config upsert endpoint now accepts HMAC server-to-server in addition to staff.
- If timer is enabled and config cannot be saved, Quiz creation reports an explicit error instead of silently creating a Quiz without countdown.


## v25.9.15.6.23 - Quiz Create Export Parity + Document Balanced Generation + HTTP MFE Config

- Sửa planner tạo Quiz từ Bank Release: tạo đúng 3 native ItemBank theo EASY/MEDIUM/HARD, `max_count` theo số câu cần hiện, không dồn tất cả vào slot đầu.
- Open edX connector cho phép `pick_count/max_count > 1` và verify theo slot.
- Bank generation chia đều quota câu hỏi theo tài liệu trước, rồi chia EASY/MEDIUM/HARD trong từng tài liệu.
- API preview/generate trả thêm `material_balancing` để kiểm tra phân bổ tài liệu.
- Thêm hướng dẫn build Learning MFE với HTTP để tránh `login_refresh` nhảy sang HTTPS khi UAT đang chạy HTTP.


## v25.9.15.6.22 - Rename Chapter Release State Cleanup Hotfix

- Fix publish Library after renaming a Chapter whose previous publish failed because of duplicate library key/name.
- Reset stale Open edX library/component state for non-published releases when expected library key changes.
- Retry import after LearningPackage missing by re-ensuring library and using connector canonical key.
- Canonicalize Content Library V2 keys in connector to match Open edX LearningPackage slug normalization.
- Add DELETE /api/question-bank-v2/releases/{release_id} for failed/unpublished release cleanup.


## v25.9.15.6.19 - Library Key Term Hotfix

- Fixed Bank Release Open edX Library keys to include the subject offering/term.
- Example: `WEB107_FA26 / Bài 2.1 / v1.0` now publishes to `lib:FPT:web107-FA26-b-i-2-1-v1-0`.
- Old stored release keys missing the term are upgraded on publish and re-imported into the correct Library when needed.
- Backend-only hotfix; no migration required.


## v25.9.15.6.14 - Bank Quiz Timer UI + FPT Naming/Grading Hotfix

- `/bank/quiz` hiển thị đầy đủ cấu hình custom timer: bật timer, thời gian làm bài, cooldown, tự nộp khi hết giờ, khóa submit.
- Tạo Quiz theo quy định FPT: Section/Bài `Bài 1` tạo Subsection `Quiz 1`, Unit luôn tên `Quiz`.
- Connector set Subsection `format=Quiz`, `graded=true` để Studio hiển thị Grade as: Quiz.
- Backend enforce naming rule, không để frontend/API cũ tạo nhầm `AI Learning Check` hoặc `Quiz tự luyện`.


## v25.9.15.6.8 - Bank Generate Cost + Loading + Audit Hotfix

- Fix prompt_cache_key quá dài bằng cách hash/sanitize về tối đa 64 ký tự.
- Thêm preview trước khi tạo câu hỏi: số câu EASY/MEDIUM/HARD, quota chapter, chi phí/token dự kiến.
- UI Tạo câu hỏi mở popup Hủy/Xác nhận; chỉ xác nhận mới gọi GPT thật.
- Thêm loading overlay khi đang tính chi phí hoặc generate.
- Quota 100 câu/chapter tính theo toàn bộ chapter, không chỉ bank version hiện tại.
- Không draft_error với đáp án gần giống nhau; chỉ bắt lỗi khi đáp án trùng hẳn.
- Trả thêm reviewed_by/reviewed_at để biết ai duyệt hoặc bỏ câu.


## v25.9.15.6.6 - Bank Review UI + Release Guard Hotfix

- Sửa danh sách câu hỏi trong Bank Chapter Workspace theo UI trang `/review`.
- Hiển thị đủ đáp án A/B/C/D và highlight đáp án đúng.
- Thêm lý do lỗi cho câu `draft_error`, nút `Bỏ câu lỗi`.
- Chặn chốt bộ đề nếu còn câu chờ duyệt hoặc câu lỗi.
- Backend `release_readiness` chặn release khi còn `draft_error`; không chỉ cảnh báo.
- Quota 100 câu/chapter tính theo tổng câu đã tạo chưa retired, kể cả câu rejected/draft_error.

# v25.9.15.6.5 - Bank Generation Flow + Chapter Quota Hotfix

- Sửa UI tạo câu hỏi trong Chapter Workspace theo hướng Bank-first nhưng giữ nguyên tinh thần course-first: tạo từ tài liệu thật, có phân bổ độ khó, qua quality check và chống trùng.
- Sửa giới hạn 100 câu/chapter: quota tính cả câu đang lỗi draft_error để không bị tạo vượt.
- Sửa backend tránh false draft_error khi model trả source_chunk_id của Bank MaterialChunk.
- Sửa format nội dung bank chunk sang Source/Type/ChunkId/BlockId giống luồng course-first.

# v25.9.15.6 - Multi-page Bank Manager UI + Exact Clone Flow

- Tách UI ngân hàng đề từ một trang `/bank` lớn thành nhiều route quản trị rõ ràng.
- `/bank` redirect sang `/bank/departments`.
- Thêm các trang: Bộ môn, Môn trong bộ môn, Phiên bản môn, Chapter theo version, Chapter Workspace, Lịch sử Quiz.
- Clone version môn giữ đúng nghĩa clone bản làm việc 100%, không clone Release, không publish Open edX, không chạy diff.
- Chapter Workspace chỉ quản lý tài liệu/câu hỏi/release; tạo Quiz để riêng ở `/bank/quiz`.
- Không thêm migration mới.



## v25.9.15.9 - Review UI + Release Assistant + Course Quiz History/Rollback

- Thêm API duyệt/bỏ câu hỏi trong Bank Version.
- Thêm duyệt hàng loạt câu pending trong Bank Version.
- Thêm endpoint đánh dấu thay đổi tài liệu đã xử lý.
- Thêm Release Readiness Assistant để chặn chốt Release khi còn tài liệu/câu hỏi chưa xử lý.
- Thêm lịch sử CourseQuizInstance và rollback best-effort.
- Thêm connector endpoint xóa Quiz node trong Studio draft.
- Cập nhật `/bank` và `/bank/quiz` theo nguyên tắc UI đơn giản cho giáo viên.
- Không thêm migration mới.

## v25.9.15.6 - Exact Subject Version Clone + Document Change Diff

- Chốt lại nghiệp vụ clone version môn: clone là copy bản làm việc 100%, không clone Release và không publish Open edX.
- Khi có `clone_from_offering_id`, backend luôn clone đủ bài/tài liệu/chunk/concept/family/câu hỏi approved sang ID mới.
- Upload tài liệu mới vào Bank Version clone sẽ đánh dấu `diff_required=true` và gợi ý kiểm tra khác biệt.
- Diff/carry-over cho phép so sánh Bank Version giữa hai kỳ khác nhau nếu có lineage clone.
- UI `/bank` bỏ clone nửa vời, giải thích rõ Release là nút chốt tay sau khi sửa xong.

## v25.9.15.3.4 - Subject Version Tree Correction

- Sửa wording và UI: `DOM123_SP25`, `DOM123_SU25`, `DOM123_FA25` là các phiên bản trực tiếp của môn `DOM123`, không có tầng container trung gian.
- UI `/bank` đổi label từ `Môn_kỳ` sang `Phiên bản môn` và hiển thị cây: Bộ môn → Môn → Phiên bản môn → Bài.
- Thêm alias API `/api/question-bank-v2/subject-versions` cho `/subject-offerings` để tên endpoint khớp nghiệp vụ hơn, vẫn giữ endpoint cũ để tương thích.
- Giữ nguyên database table `ai_subject_offerings`, nhưng metadata mới dùng `architecture=subject_version_tree`.
- Cập nhật docs và test để xác nhận Chapter/Bài nằm dưới trực tiếp từng subject version như `DOM123_SP25`.

## v25.9.15.3.3 - Term Offering Codes + Clone Subject Term

- Chuẩn hóa `phiên bản môn` thành term offering với 3 kỳ/năm: `SPyy`, `SUyy`, `FAyy`.
- Backend tự sinh code dạng `DOM123_SP25`, `DOM123_SU26`, `DOM123_FA27`.
- Cho phép tạo phiên bản môn mới bằng cách clone từ phiên bản môn cũ.
- Clone tạo bản ghi mới cho Chapter, Bank Version, Material Version, Material Chunk, Concept Version, Question Family và approved questions.
- Câu hỏi clone sang kỳ mới giữ `status=approved`, có `previous_question_id`, không giữ Open edX component/library ID cũ.
- Không clone Bank Release/Open edX Library; release mới vẫn phải publish ra library riêng theo nguyên tắc 1 Bank Release = 1 Open edX Library.
- UI `/bank` thêm chọn kỳ SP/SU/FA và clone từ phiên bản môn có sẵn.


## v25.9.15.3.2 - Subject Version Version Isolation + Approved Carry-over

- Thêm lớp `môn_su/phiên bản môn` (`ai_subject_offerings`) nằm giữa Môn và Chapter.
- Coi `môn_su/kỳ` là version triển khai của môn; chapters có thể gắn vào offering.
- Carry-over clone câu từ version cũ sang version mới và đặt `approved` luôn.
- Câu không còn dùng được không clone vào version mới; không tạo retired snapshot ở version mới.
- Concept/Family tiếp tục là metadata lõi gắn với câu hỏi, không phải tầng UI điều hướng.
- Thêm migration `0013_v25_9_15_3_2_subject_offering_version_isolation.py`.


## v25.9.15.3 - Version Diff / Carry-over / Retire Questions

- Added Bank Version diff preview between old and new versions.
- Added lineage fields to `ai_questions`: previous question, lineage root, revision number, carry-over and retired state.
- Added `ai_bank_version_diffs` and `ai_bank_version_diff_items` tables.
- Added carry-over API that copies approved questions into the new Bank Version without modifying the old version.
- Added retire API for marking questions as no longer suitable when source materials change.
- Updated `/bank` with a guided version comparison step.


## v25.9.15.2 - Bank Material Upload + Generate from Bank Version

- Added `ai_material_chunks` and migration `0011_v25_9_15_2`.
- Added Bank Version material upload endpoint with safe file size/type checks and local storage.
- Added extraction/chunking for uploaded bank materials using existing ContentExtractor/Chunker.
- Added generate-from-bank-version endpoint that calls ModelGateway and creates `ai_questions` scoped to `bank_version_id`.
- Added concept version and bank question family linking during bank generation.
- Updated `/bank` UI with a simple Upload → Generate step before Release.
- Kept generated questions in review-first flow; no automatic release publish without teacher review.


## v25.9.15.0 - Versioned Question Bank First Architecture

- Thêm mô hình Bộ môn / Môn / Chapter / Bank Version / Material Version / Bank Release.
- Áp dụng nguyên tắc `1 Bank Release = 1 Open edX Library`.
- Thêm mapping Open edX course vào subject/chapter/release để nhiều khóa học dùng chung một ngân hàng đề đã duyệt.
- Thêm các cột nullable vào `ai_questions` để gắn câu hỏi cũ vào bank-first mà không phá luồng course-first hiện tại.
- Thêm API `/api/question-bank-v2/*` và UI `/bank`.
- Giữ nguyên native Ulmo ItemBank connector từ v25.9.14.6.1; bản này tập trung vào versioned bank architecture.

# v25.9.14.6.1 — Parent Locator String Hotfix

- Sửa native Studio `create_xblock`: truyền `parent_locator` dạng serialized string thay vì `BlockUsageLocator`.
- Áp dụng cho cả tạo `itembank` và tạo `problem` child.
- Không thay đổi DB/API/UI.

# v25.9.14.6 - Native Ulmo ItemBank Auto Insert + Guided Workflow

- Thay block sai `library_content`/Randomized Content bằng native Problem Bank Beta `itembank` trên Ulmo.3.
- Mô phỏng đúng luồng Studio: tạo `itembank`, thêm từng `problem` child tuần tự, đặt `upstream`, gọi `sync_library_content`.
- Verify bắt buộc block type, `max_count=1`, child count, parent, upstream và chống component trùng giữa các slot.
- Rollback các node vừa tạo nếu một slot/component lỗi; không báo thành công một phần.
- Tự dọn chỉ các legacy AI Randomized Content Block có block ID `problem-bank-slot-*`.
- Backend chỉ chấp nhận kết quả `native_ulmo_itembank` đã verify; từ chối legacy/unverified response.
- UI `/export` đổi thành quy trình 3 bước, ẩn tùy chọn kỹ thuật và luôn tạo Quiz + native Problem Bank trong luồng chính.
- Không có migration mới. Thêm tài liệu/test report tại `docs/V25_9_14_6_NATIVE_ULMO_ITEMBANK_GUIDED_WORKFLOW.md`.

# v25.9.14.5.1 - create_child return normalization hotfix

- Fix Ulmo.3 CMS connector when modulestore `create_child` returns a usage-key string instead of an XBlock descriptor.
- Resolve the returned key to the real draft XBlock before calling `update_item`.
- Re-read the parent after a partial create failure to avoid duplicate retry-created blocks.
- Add clearer diagnostics for raw return type/value and resolved usage key.
- This hotfix fixes the reported `'str' object has no attribute 'block_type'` failure only; selected-component attachment for `library_content` still requires live Ulmo.3 verification.

## v25.9.14.5 - Stable Family Reconciliation + Deterministic Hard Duplicate Guard

- Không gọi GPT/OpenAI khi tính Family Slot Plan. Planner dùng `concept_key/concept_id/concept_title` đã có từ bước trích xuất/generate.
- Backend là nguồn sự thật của `question_family_id`: dạng `fam-v1-*`, ưu tiên `concept_id` rồi `concept_key`, legacy family root chỉ làm fallback; tuyệt đối không chứa `variant_no` hoặc question ID và reconcile chạy idempotent.
- Thêm migration `0008_v25_9_14_5_stable_family_reconciliation.py` để backfill family ID cũ và đánh lại `variant_no` tuần tự.
- Trước preview, backend tự reconcile family để sửa dữ liệu mới/cũ chưa chuẩn; response ghi rõ số family trước/sau và không dùng LLM.
- Stable family luôn nằm trọn trong đúng một Problem Bank slot; không lặp và không tách cùng family sang nhiều slot.
- Khi family ít hơn số slot yêu cầu, giảm số slot thay vì lặp/tách family. Khi family nhiều hơn slot, bin-pack nhiều family vào slot và vẫn dùng mọi câu duy nhất đúng một lần.
- Hard Duplicate Guard chặn trùng `question_id`, Open edX component, nội dung normalize và stable family ở trong hoặc giữa các slot.
- Câu hỏi trùng chính xác chỉ giữ một canonical record để không tăng trọng số random; các câu duy nhất approved/published còn lại đều được sử dụng.
- Đổi nút UI thành **Tính kế hoạch tối ưu** và hiển thị rõ **Gọi GPT: Không**.
- Family ID và Variant trong form review chuyển sang read-only vì backend tự quản lý.
- Thêm index `ix_ai_questions_course_chapter_family_difficulty`.
- Thêm test report trung thực tại `docs/V25_9_14_5_TEST_REPORT.md`.

## v25.9.14.4.1 - Usage Key Normalization Hotfix

- Fix CMS Quiz Node Creator returning JSON-quoted opaque usage keys such as `"block-v1:..."`.
- Normalize usage keys at CMS connector, AI connector client, and publisher boundaries.
- Automatically repair the local `ai_course_sync_state` row created with a quoted Unit key when Problem Bank insertion is retried.
- Prevent `UsageKey.from_string` validation failures before Problem Bank creation.
# v25.9.14.4 - Problem Bank Auto Insert

- Added AI Server endpoint `POST /api/publish/courses/{course_id}/cms-problem-banks/insert` to insert Family Slot Plan as Problem Bank / `library_content` blocks into a real Quiz Unit.
- Added CMS connector endpoint `POST /api/ai-connector/v1/courses/{course_id}/problem-banks`.
- Added `/export` UI flow **Tạo Quiz + Problem Bank** and **Chỉ insert Problem Bank**.
- Backend validates that slot questions were already published to one Chapter Library before inserting blocks.
- Connector verifies created blocks by reading back `source_library_id`, `max_count`, `manual`, `shuffle`, and selected component fields when available.
- If selected components cannot be verified on Ulmo.3, the API returns `manual_component_selection_required=true` instead of pretending success.
- No DB migration required.

# v25.9.14.3 - CMS Quiz Node Creator

- Added real CMS/Studio quiz node creation endpoint in AI Server: `POST /api/publish/courses/{course_id}/cms-quiz-node/create`.
- Added real CMS connector endpoint: `POST /api/ai-connector/v1/courses/{course_id}/quiz-nodes`.
- Added `/export` UI section for selecting a synced CMS node and creating a draft Quiz node in Studio.
- Fails closed when `USE_MOCK_OPENEDX=true`, parent node type is unsupported, or CMS connector does not return a real `usage_key`.
- No DB migration required. Problem Bank block insertion remains explicitly deferred to v25.9.14.4.


## v25.9.14.1 - Question Family ID

- Thêm `question_family_id`, `variant_no`, `source_evidence` vào `ai_questions`.
- Prompt/model schema yêu cầu sinh family id và variant number cho câu hỏi cùng concept/difficulty.
- Backend fallback tự tạo family ổn định nếu model chưa trả family.
- Review UI hiển thị Concept/Family/Variant và form sửa cho phép chỉnh family thủ công.
- Thêm migration `0007_v25_9_14_1_question_family_id.py`.

## v25.9.13.52 - Analytics PostgreSQL GROUP BY Fix

- Fixed `/api/analytics/overview` HTTP 500 on PostgreSQL caused by duplicate SQLAlchemy bind parameters inside `coalesce(ai_questions.topic, 'unknown')` between SELECT and GROUP BY.
- Reused one labeled SQL expression with a literal SQL constant for dashboard `top_scopes`.

## v25.9.13.51 - Next.js SWC Debian Slim Fix

- Switched frontend Dockerfile from `node:20-alpine` to `node:20-bookworm-slim`.
- Fixes production Docker builds where Next.js attempts to load `@next/swc-linux-x64-gnu` but Alpine lacks `ld-linux-x86-64.so.2`.
- Keeps CMS auto session login behavior from v25.9.13.49/50.

# Changelog

## v25.9.13.50 - Auto CMS Session Login

- AI Server tự chuyển qua CMS session bridge nếu user chưa có phiên AI.
- User đã đăng nhập CMS/Open edX sẽ tự có phiên trong AI Server, không cần nhập lại JWT.
- Thêm `NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN` để bật/tắt auto-login.
- Token AI ngắn hạn chỉ lưu trong sessionStorage, không lưu localStorage.



## v25.9.13.48 - CMS session bridge SSO

- Thêm endpoint CMS plugin `/session/bridge` và `/session/me`.
- Thêm backend endpoint `/api/auth/openedx-session/exchange` để đổi CMS session ticket thành AI JWT.
- Thêm frontend callback `/auth/cms-callback` và nút “Dùng phiên CMS”.
- Cho phép user đã đăng nhập CMS/Open edX vào AI Server không cần đăng nhập lại hoặc tự dán JWT.

## v25.9.13.46 - Alembic clean rebuild fix

- Fixed backend startup failure on a clean PostgreSQL volume caused by `0002_chapter_libraries` recreating `ai_course_libraries` after `0001_initial_schema` had already created it from current SQLAlchemy metadata.
- Made `0002_chapter_libraries` idempotent for table, columns and legacy unique constraint creation.

## v25.9.13.45 - Frontend standalone Docker fix

- Enabled `output: 'standalone'` in `frontend/next.config.js` so Docker can copy `.next/standalone` after `next build`.
- Kept production Docker runtime on `node server.js` from the standalone output.


## v25.9.13.44 - Frontend Docker Build Fix

- Fix frontend Docker build failure `sh: tsc: not found`.
- Force Docker deps stage to install build dependencies with `npm ci --include=dev`.
- Verify `tsc` and `next` binaries in the image before build.
- Normalize frontend package-lock resolved URLs to npm public registry for clean local rebuilds.


## v25.9.13.43 - Full rebuild hardening

- Fixed SQLAlchemy metadata startup issue in `QuestionEmbedding` indexes.
- Rebuilt production Docker/Compose flow for clean builds: PostgreSQL, Redis, backend, worker and production Next.js frontend.
- Added stronger production config validation for DB/OpenAI/Open edX OAuth placeholders.
- Added from-scratch deployment guide and helper scripts for secrets/Tutor CMS env injection.

## v25.9.13.42 - Scale and maintainability pass

- Added production composite indexes for question, job, chunk, course sync, usage and publish queries.
- Added explicit Open edX lifecycle fields so teacher review status is no longer overloaded with publish/verify/delete state.
- Added Idempotency-Key handling for generation, course publish, single-question publish and rollback flows.
- Added row-lock guards for generation and publish/rollback state transitions.
- Moved analytics dashboard aggregation from Python list aggregation to SQL aggregation.
- Changed upload validation to stream uploaded files in bounded chunks before parsing.
- Added standardized API error envelope and CI quality gates.
- Split the large Sync page by moving reusable sync tree/search/content widgets to `components/sync/SyncCourseWidgets.tsx`.

See `docs/RELEASE_v25.9.13.42_SCALE_MAINTAINABILITY.md` for deployment notes.

## v25.9.13.53 - Level 1 same-server Tutor network deployment

- Changed production compose to run AI Server as separate containers on the Tutor/Open edX Docker network.
- Removed direct host port publishing from production backend/frontend; reverse proxy should route to `ai-backend:8000` and `ai-frontend:3000`.
- Added stable container names and network aliases for Caddy/Nginx routing.
- Added Tutor Caddy reverse proxy plugin and Caddy/Nginx snippets.
- Added Level 1 deployment guide and network health-check script.

## v25.9.14.1 - Concept-Aware Generation

- Thêm bảng `ai_concepts` để lưu concept/vấn đề học tập theo course/node.
- Thêm API `GET/POST /api/courses/{course_id}/concepts` để xem/trích xuất concept.
- Thêm concept panel trong `/sync`.
- Generation Planner tự thêm `Concept-aware generation hints` vào prompt.
- Prompt/JSON schema/Question model có thêm `concept_id`, `concept_title`, `concept_key`.
- Thêm migration `0006_v25_9_14_0_concepts.py`.


## v25.9.15.1 - Safe Mapping Guard + Bank Release Publish Wiring

- Added mapping validation endpoints for Open edX course and chapter mappings.
- Course code must match subject code before mapping is saved.
- Chapter mapping requires a published Bank Release and a valid Open edX node usage key.
- Added release publish endpoint that imports approved Bank Version questions into the release-specific Open edX Library.
- Release is only marked published after Open edX import succeeds.
- Added validation metadata columns to course/chapter mappings.
- Updated /bank UI with Publish Library, Validate Mapping, and Validate Chapter workflow.

## v25.9.15.3.1 - Version Isolation Carry-over Hotfix

- Treat Bank Version v1 and v2 as independent snapshots.
- Retire action from diff now creates/marks a retired snapshot in the target version, never mutates the source version.
- UI now calls retire endpoint with `to_bank_version_id`.

## v25.9.15.3.4.2 - Migration Idempotency Hotfix

- Fixed fresh/cleared DB migration failure where legacy `0001_initial_schema` created current metadata columns before historical migrations ran.
- Made migrations `0006_v25_9_14_0_concepts.py` and `0007_v25_9_14_1_question_family_id.py` idempotent for duplicate tables, columns, and indexes.

## v25.9.15.6.1 - Bank UI Usability Hotfix

- Chuyển form thêm Bộ môn/Môn/Version/Bài vào popup cạnh ô tìm kiếm.
- Thêm bài chỉ cần nhập tên, hệ thống tự sinh số bài/ID.
- Workspace bài tự khởi tạo, bỏ nút “Bắt đầu”.
- Sửa upload tài liệu Bank Version dùng FormData đúng cách.
- Thêm xem/xóa tài liệu đã upload.
- Tự chạy kiểm tra thay đổi tài liệu và hiện kết quả bằng popup.
- Tạo câu hỏi có chỉ tiêu và chặn vượt chỉ tiêu.
- Chốt Release tự sinh mã release, không bắt người dùng nhập.
- Danh sách câu hỏi đổi sang thẻ dễ đọc hơn.

## v25.9.15.6.2 - Chapter Name Input Hotfix

- Sửa popup thêm bài: chỉ nhập phần sau chữ `Bài`, ví dụ `1`, `2`, `1.1`, `1.2`.
- Hệ thống tự tạo tên bài dạng `Bài {giá trị nhập}`.
- Không còn hiển thị/nhắc `số bài` cho giáo viên.
- Ưu tiên hiển thị `chapter.title` trong danh sách bài, breadcrumb, workspace, release title, library key và quiz title.
- `chapter_no` giữ vai trò nội bộ để sắp xếp/unique, không phải dữ liệu người dùng phải nhập.

## v25.9.15.6.3 - Bank UI Delete + Popup + 100 Question Limit Hotfix

- Fixed material delete API crash caused by missing `_require_mutable_bank_version`.
- Hardened modal/popup layout for Bank management screens.
- Enforced 100 questions/chapter default limit in both frontend and backend.
- Removed separate Change Check and Release panels from chapter workspace.
- Moved quick actions to top action bar.

## v25.9.15.6.4 - Bank Popup Document Preview Hotfix

- Sửa popup xem tài liệu trong `/bank/chapters/{chapterId}`.
- Không còn render mỗi chunk thành một box cuộn riêng.
- Gộp nội dung tài liệu thành một vùng đọc duy nhất.
- Khóa scroll nền khi popup mở.
- Thêm ESC để đóng popup.
- Không thêm migration, không đổi API backend.

## v25.9.15.6.7 - Bank Question Edit Popup Hotfix

- Thêm nút Sửa vào từng thẻ câu hỏi trong Bank Chapter Workspace.
- Thêm popup chỉnh sửa câu hỏi theo hướng UI `/review`.
- Thêm API PATCH để sửa câu hỏi trong `question-bank-v2`.
- Backend validate đủ câu hỏi, đủ 4 đáp án và đáp án đúng A/B/C/D.
- Câu `draft_error` sau khi sửa được đưa về `pending_review` nếu không chọn trạng thái khác.
- Không cho sửa câu đã `published`.

## v25.9.15.6.9 - Bank Dashboard + Review Status + Quick Search

- `/bank` thành Dashboard tổng quan thay vì redirect thẳng vào danh sách bộ môn.
- Thêm quick search tìm nhanh bộ môn/môn/version/bài.
- Thêm summary API cho bộ môn, môn, version môn, chapter.
- Card bộ môn/môn/version/chapter hiển thị rõ đã duyệt xong/chưa duyệt xong, câu chờ xử lý, bài sẵn sàng chốt.
- Workspace chapter thêm khối “Bạn cần làm gì tiếp?”.
- Bỏ/Bỏ câu lỗi bắt nhập lý do trong popup để lưu review/audit phục vụ truy vết và fine-tune AI.
- Không thêm migration mới.

## v25.9.15.6.10 - Bank Dashboard Count + Refresh Auth Hotfix

- Fix dashboard count: “còn việc” chỉ tính nơi có câu chờ duyệt/câu lỗi.
- Fix dashboard done/not-done: `đã xong = tổng - còn việc`.
- Fix F5 401 Unauthorized by reading AI session token from `sessionStorage` inside `authHeaders()` before React state finishes hydration.
- Guard `/bank` overview load to avoid duplicate `dashboard/overview` request for the same auth headers.
- No database migration.

## v25.9.15.6.11 - Bank Quiz Auto Map by Course ID

- Sửa `/bank/quiz` theo hướng người dùng chỉ cần dán Course ID.
- Backend tự tìm môn từ Course ID, tự tìm version môn phù hợp đã có Release published đủ tất cả bài.
- Backend đọc Section Open edX và tự map Section vào Bài cùng tên.
- Thêm API `/quiz/auto-map/preview` và `/quiz/auto-map/apply`.
- UI `/bank/quiz` bỏ form chọn nhiều tầng Bộ môn/Môn/Version/Bài/Release/Node thủ công.
- UI hiển thị bảng map Bài ↔ Section ↔ Release, có nút tạo Quiz từng bài và tạo toàn bộ.
- Không thêm migration.

## v25.9.15.6.12 - Bank Quiz Version Picker by Course ID

- `/bank/quiz` vẫn tự đọc Course ID để nhận môn/kỳ, nhưng không khóa cứng version theo Course ID.
- Sau preview, UI hiển thị dropdown các version môn của môn tìm được.
- Hệ thống pick sẵn version khớp Course ID, ví dụ `WEB107_SU25`.
- Giáo viên có thể đổi sang version khác cùng môn, ví dụ `WEB107_SU24`, nếu version đó đã có Release published đủ tất cả bài.
- Backend validate `selected_subject_offering_id` thuộc đúng môn và đủ điều kiện publish before map/apply.
- Dropdown disable version chưa đủ điều kiện và hiển thị số bài đã publish.
- Không thêm migration.

## v25.9.15.6.13 - Custom Timed Practice Quiz

- `/bank/quiz` có thêm cấu hình timer cho Quiz tự luyện.
- Không dùng native Open edX Timed Exam.
- AI Server lưu timer config vào metadata của CourseQuizInstance.
- Connector best-effort ghi config sang plugin `openedx_unit_reset`.
- Plugin `openedx_unit_reset` thêm UnitQuizTimerConfig, UnitQuizSession, quiz-session APIs, runtime JS và middleware chặn submit sau hết giờ.

## v25.9.15.6.16 - Multi Source Chunk Reference Hotfix

- Fixed `invalid_source_chunk` false draft errors when AI returns multiple source chunks in one field, e.g. `chunkA;chunkB`.
- Added backend helper to split/normalize multi chunk references separated by `;`, `,`, `|`, or newline.
- Quality checker now validates each chunk id individually and reports only actual missing ids.
- Course-first source node resolution now uses the first existing chunk when a question references multiple chunks.
- Source trace API now returns both the first `chunk` for backward compatibility and a new `chunks` list for all referenced chunks.
- Bank-first generation now recognizes multi MaterialChunk ids and does not pass them to the course ContentChunk validator.

## v25.9.15.6.17 - Quiz Create Existing Mapping Guard Hotfix

- Fixed `/api/question-bank-v2/releases/{release_id}/quiz/create` rejecting a valid saved `course_chapter_mapping_id` with `existing_chapter_mapping`.
- Quiz creation now allows reusing the exact mapping row selected from `/bank/quiz`.
- Duplicate mapping protection remains active if validation points to a different mapping row.
- No database migration.

## v25.9.15.6.18 - Bank Entity Actions + Empty Delete Guard

- Add `...` action menu on Department, Subject, Subject Version, and Chapter cards.
- Add basic edit APIs for code/name/description/title.
- Add delete APIs guarded by "empty only" checks.
- Prevent deleting entities that already contain child data such as chapters, bank versions, materials, questions, releases, Open edX mappings, or created quizzes.
- No database migration required.

## v25.9.15.6.20 - Bank Entity Action Menu Click Hotfix
- Fixed entity action menu not opening on Bộ môn / Môn / Phiên bản môn / Bài cards.
- Replaced broken `details/summary` toggle with a controlled React button menu.
- Changed visible trigger from `...` text to `⋮` icon.
- Prevented menu clicks from navigating into the card.
- Raised menu z-index so it appears above neighboring cards.

## v25.9.15.6.21 - Library LearningPackage Canonical Key Hotfix

- Fix publish/import problem failed with `LearningPackage matching query does not exist` on Open edX Content Libraries V2.
- Connector now canonicalizes the library key using the actual key returned by Open edX after ensure/create library.
- AI Server updates release.openedx_library_key before importing problem components when connector returns a canonical key.
- No migration required.

## v25.9.15.6.24 - Quiz Slot Concept Balance Hotfix

- Reworked Bank Release quiz planner from 3 difficulty banks into exact visible-question slots.
- Each requested quiz question is now represented by one native ItemBank slot with `pick_count=1` and `max_count=1`.
- Ensures a question/component is never assigned to more than one slot.
- Keeps a concept/family wholly inside one slot when there are enough concepts/families.
- When concepts/families exceed the number of slots, bin-packs whole concepts into slots to balance candidate question counts.
- When concepts/families are fewer than required slots, uses soft split of large concepts only to satisfy exact EASY/MEDIUM/HARD counts and emits warnings.
- No database migration.

## v25.9.15.6.27 - FPT Light Orange Theme Polish

- Đổi theme AI Server sang tông cam nhạt + trắng phù hợp nhận diện FPT.
- Sidebar chuyển từ nền tối sang nền trắng/cam nhạt, active item rõ hơn bằng viền/cam gradient.
- Chuẩn hóa button, input focus, card, alert, toggle, quiz workbench, table header theo palette cam nhạt.
- Giữ layout /bank/quiz 2 cột sticky settings từ v25.9.15.6.26, chỉ polish giao diện.

## v25.9.15.6.29 - Modern White UI Refresh

- Removed the FPT orange-tint theme as the primary UI surface.
- Switched the app shell, sidebar, cards, quiz workbench, forms, tables and alerts to a clean white SaaS-style theme.
- Kept a restrained blue accent for primary actions, focus states and active navigation.
- Improved visual hierarchy with neutral borders, subtle shadows, cleaner hover states and better table readability.
- No backend or database migration required.


## v25.9.15.6.30 - Bank Quiz Focused Navigation + Create Confirm UX

- Sidebar: tạm ẩn nhóm Tạo & duyệt cũ để tập trung vào luồng Ngân hàng đề.
- Sidebar Vận hành: đổi nhãn theo luồng mới: tổng quan vận hành, tiến trình job, nhật ký thao tác.
- Sidebar Quản trị: Người dùng nhấn mạnh theo dõi giáo viên làm việc.
- /bank/quiz: bỏ ghi chú FPT naming cố định trong panel timer; chuyển thành popup xác nhận khi tạo Quiz.
- /bank/quiz: nút tạo hàng loạt rút gọn thành “Tạo Quiz (X)” và popup tóm tắt Course ID, số câu, độ khó, timer, naming.
- Settings: đổi “Giới hạn tạo câu hỏi theo khóa học” thành “Giới hạn tạo câu hỏi theo Bài (Chapter)”.
- Settings: bỏ khối “Phân quyền demo” khỏi UI quản trị.

## v25.9.15.6.31.1 - Build Fix for Bank Quiz Popup String

- Fixed `frontend/app/bank/quiz/page.tsx` TypeScript build failure caused by an unterminated string literal in the quiz confirmation popup formatter.
- No backend/database changes.

## v25.9.15.6.31.3 - Bank Quiz Create Popup Settings UX

- Moved question plan and practice quiz timer settings out of the right-side `/bank/quiz` panel.
- Creating one quiz or bulk quiz now opens a reusable modal popup where users can edit question count, difficulty ratio, timer duration, retake cooldown, auto-submit and lock options.
- Right-side panel now focuses on Course ID, version detection, saving configuration and a compact current-settings summary.
- Reused the existing bank modal/popup pattern so future create/edit flows should follow the same UX pattern.

## v25.9.15.6.31.6 - Bank-first Operations Backend Audit Hotfix

- Audited the Operations/Admin pages after the navigation was changed to the Bank-first flow.
- Replaced `/dashboard` data source from legacy course-first analytics to Bank dashboard + Quiz instances + global audit/job data.
- Updated `/jobs` to show global Generate jobs, CourseQuizInstance history, and publish/quiz/rollback audit activity.
- Updated `/audit` to read global audit logs by default so Bank actions without course_id are not hidden.
- Expanded audit action labels for question_bank.* actions.
- Updated `/users` to track teacher work from audit logs: bank actions, quiz creation, release publish, rollback, and failures.
- Removed remaining demo-role wording from the user analytics permission warning.


## v25.9.15.6.31.9 - Chapter quota backend + version capacity fix

- Fixed Bank-first quota to use chapter default policy instead of old course-first policy.
- Fixed version cards showing `total_questions/100`; they now show total capacity across all chapters.
- Fixed generate preview/create to pass the configured chapter limit instead of hard-coded 100.

## v25.9.15.6.31.10 - Light/Dark Theme + Landing Page + Footer

- Added light/dark theme toggle with `localStorage` persistence and `html[data-theme]` styling.
- Added app footer to authenticated app pages.
- Added public landing page at `/` instead of redirecting immediately to dashboard.
- Landing page introduces Open edX AI Server, Bank-first workflow, Quiz creation, operations tracking, and CTA links.
- Skips automatic CMS session bridge redirect on `/` so the landing page is visible at `http://ai.cms-test.poly.edu.vn/`.

## v25.9.15.6.31.11 - Remove dark/landing and rebuild Bank dashboard

- Removed dark theme toggle and landing shell from the app runtime.
- Changed `/` to redirect to `/bank`.
- Rebuilt `/bank` into a stronger Bank-first command center with useful KPI cards, review progress, charts, recent Quiz feed, recent job feed and audit log.
- Kept footer but removed the theme controls.
