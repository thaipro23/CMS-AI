

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
