# Dash-CMS — chỉ mục mã nguồn

Cập nhật: 06/09/2026. Nhánh làm việc: `feat/import-quiz-cms-old-su26`; nền rà soát: sau `2e2c187`.
Đây là bản đồ tìm mã nguồn, không phải xác nhận đã triển khai production. Khi tiếp tục, luôn đọc `git status`, `git diff`, rồi `git fetch origin` trước khi chọn HEAD mới.

## Tìm nhanh theo lỗi

| Cần sửa | Điểm vào chính | Phần liên quan |
| --- | --- | --- |
| Admin thiếu quyền hoặc quyền bị thu hồi chưa có hiệu lực | [get_user_context](backend/app/core/rbac.py) | [BusinessRBACService](backend/app/services/business_rbac.py), [xác thực JWT](backend/app/core/security.py), [SSO](backend/app/api/routes/auth.py) |
| Menu hiện nhưng API trả 403 | [AppShell](frontend/components/layout/AppShell.tsx) | [AppContext](frontend/context/AppContext.tsx), [academic route guards](backend/app/api/routes/academic.py), [RBAC API](backend/app/api/routes/rbac.py) |
| Cấp/thu hồi Chủ cơ sở | [trang Người dùng](frontend/app/users/page.tsx) | `can_grant`, `list_assignments`, `revoke_assignment` trong BusinessRBACService; `can_revoke` trong response danh sách |
| Thông báo tiếng Anh, mã lỗi trong câu hướng dẫn | [userFacingError](frontend/lib/userFacingError.ts) | [API parser](frontend/lib/api.ts), [backend error handlers](backend/app/core/errors.py) |
| Thông báo bị đè hoặc nằm sau hộp thoại | [ActionMessage](frontend/components/ui/ActionMessage.tsx), [InlineNotice](frontend/components/ui/InlineNotice.tsx) | [CSS module thông báo](frontend/components/ui/FeedbackMessage.module.css), [AccessibleDialog](frontend/components/ui/AccessibleDialog.tsx) |
| Sai trạng thái tác vụ | [PersistentJobNotice](frontend/components/ui/PersistentJobNotice.tsx) | [Jobs](frontend/app/jobs/page.tsx), [worker](backend/app/worker.py) |
| Bố cục chung, tiêu đề lặp, trang mất class CSS | [PageShellContext](frontend/components/layout/PageShellContext.tsx) | [AppShell](frontend/components/layout/AppShell.tsx), [EnterpriseDesignContract](frontend/components/layout/EnterpriseDesignContract.tsx) |
| Bảng tràn ngang, cột/nút bị che | [EnterpriseDataTable](frontend/components/table/EnterpriseDataTable.tsx) | [TableStates](frontend/components/table/TableStates.tsx), [OperationsWorkspace](frontend/components/operations/OperationsWorkspace.tsx) |
| Import Quiz CMS cũ | [page](frontend/app/import-quiz-cms-old/page.tsx), [CSS module](frontend/app/import-quiz-cms-old/page.module.css) | [legacy_quiz_import](backend/app/services/question_bank/legacy_quiz_import.py), [question-bank-v2 routes](backend/app/api/routes/question_bank_v2.py) |
| Tạo Quiz: số câu, độ khó, 0%, preview cũ | [Quiz page](frontend/app/bank/quiz/page.tsx) | [quiz_creation](backend/app/services/question_bank/quiz_creation.py), `bank_quiz_create_task` trong worker |
| Final test lỗi nhưng CMS đã sạch, Dash vẫn khóa tạo lại | [rollback workflow](backend/app/services/question_bank/release_publish.py) | Đối chiếu cây Course CMS trước khi đóng `rollback_manual_required`; giữ khóa nếu CMS không đọc được hoặc còn node; [quiz recovery tests](backend/app/tests/test_quiz_recovery.py) |
| Admin bị 403 khi đồng bộ điểm qua worker | [requester context](backend/app/api/routes/academic.py) | [worker rehydration](backend/app/worker.py), [academic access](backend/app/services/academic/access.py); giữ bằng chứng admin tin cậy qua queue và vẫn đọc lại DB grant |
| Thông báo sau thao tác không nhìn thấy | [FeedbackProvider](frontend/components/ui/FeedbackProvider.tsx) | Toast giữ lỗi/cảnh báo đến khi đóng; `InlineNotice` vẫn là kết quả bền vững |
| Modal nhắc sinh viên bị cắt, không cuộn | [class detail](frontend/app/student-management/classes/[classId]/page.tsx) | [ProgressEmailDialog.module.css](frontend/components/student-management/ProgressEmailDialog.module.css) |
| Import Quiz các card chồng lên nhau | [Import CSS module](frontend/app/import-quiz-cms-old/page.module.css) | Page grid dùng hàng tự nhiên, không co WorkspaceSection dài; [operational E2E](e2e/tests/operational-recovery-layout.spec.ts) |
| Final test dồn quá nhiều câu vào một Bài | [quiz_creation](backend/app/services/question_bank/quiz_creation.py) | `final_test_all_chapter_releases_itembank_v2`; pool lớn được tách thành nhiều Problem Bank, phân bổ cân bằng theo từng Bài và giới hạn câu khả dụng |
| Dữ liệu sinh viên/giảng viên sai phạm vi | [academic/access](backend/app/services/academic/access.py) | [roster](backend/app/services/academic/roster.py), [teacher_report](backend/app/services/academic/teacher_report.py), [AcademicService](backend/app/services/academic_service.py) |
| Tiến độ Udemy ở chi tiết lớp | [UdemyClassProgressPanel](frontend/components/student-management/UdemyClassProgressPanel.tsx) | [udemy_progress](backend/app/services/academic/udemy_progress.py); request bắt buộc giữ `class_id` |
| Lấy danh mục môn/cơ sở, POLY/PTCD, kỳ học | [APAcademicClient](backend/app/services/ap_academic_sync.py) | [academic/ap_sync](backend/app/services/academic/ap_sync.py), [subject_delivery](backend/app/services/academic/subject_delivery.py) |

## Quyền nghiệp vụ

| Vai trò | Phạm vi/quyền chính | Có thể cấp quyền |
| --- | --- | --- |
| SYSTEM_ADMIN | Toàn bộ hệ thống, bao gồm các permission mới trong danh mục; bỏ giới hạn course khi đã xác minh là admin | Tất cả vai trò và phạm vi hợp lệ |
| CAMPUS_OWNER — tất cả cơ sở | Vận hành đào tạo, AP Sync, Cơ sở, Học kỳ, Quản lý môn học, Người dùng & phân quyền | CAMPUS_OWNER tại từng cơ sở cụ thể |
| CAMPUS_OWNER — từng cơ sở | Lớp, sinh viên, giảng viên, báo cáo và thao tác đào tạo trong cơ sở được giao | Không cấp quyền |
| DEPARTMENT_HEAD | Ngân hàng đề, tạo/duyệt câu hỏi, Release, Quiz trong bộ môn | Chủ môn và Người duyệt trong phạm vi |
| SUBJECT_OWNER | Ngân hàng đề, Release, Quiz trong môn/phiên bản môn | Người duyệt trong phạm vi |
| QUESTION_REVIEWER | Xem, sửa, duyệt/từ chối câu hỏi được giao | Không cấp quyền |
| TEACHER_ASSIGNED | Xem lớp được AP phân công | Không cấp quyền |

`CAMPUS_OWNER` toàn cơ sở được biểu diễn bằng `CAMPUS:*` hoặc `SYSTEM`. Gói mở rộng gồm `academic.catalog.manage`, `campus_owner.assign`, `rbac.view`; không cấp quyền ngân hàng đề hoặc cài đặt kỹ thuật. `CAMPUS_MANAGER` là tên cũ, chỉ giữ để đọc quyền hiện có. Phạm vi cơ sở dùng `campus_code`, không phải UUID hoặc tên hệ POLY/PTCD.

Menu chỉ giúp điều hướng; quyền thực tế phải được chặn tại API/service. Quyền `SYSTEM_ADMIN` từ DB được giải quyết lại mỗi request; claim `is_staff` riêng lẻ không đủ quyền admin.

## Luồng tạo Quiz

1. Chọn phiên bản môn, Release, bài/đích Open edX, tổng số câu và tỷ lệ Dễ/Trung bình/Khó.
2. Preview lấy lại khi cấu hình thay đổi; response cũ không được ghi đè preview mới.
3. Planner chọn đủ câu theo độ khó. Luồng tạo Quiz không có quota theo loại câu hỏi; loại câu gốc trong Release được giữ nguyên. Với câu nhập tay/import không có concept, hệ thống lấy theo pool độ khó (ví dụ 10 Dễ + 5 Trung bình); nếu tổng kho đúng bằng số cần tạo thì lấy đủ 10/10. Final test gom nhiều Bài/Release nhưng tách pool lớn thành nhiều Problem Bank và vẫn giữ tổng `pick_count` chính xác.
4. Dữ liệu import cũ có thể cân lại độ khó khả dụng khi thiếu câu Khó; câu native vẫn chịu quy tắc độ khó. Không tự biến câu multi-select thành single-select.
5. Worker giữ giá trị `0` của tỷ lệ độ khó/thời gian chờ; chỉ dùng mặc định nếu thiếu hoặc `null`.
6. Release đã xuất bản thành công giữ quy tắc khóa. Việc chuẩn hóa thông báo không bỏ kiểm tra nội dung hoặc readiness.

Các model/schema nằm tại [question_bank model](backend/app/models/question_bank.py), [question_bank schema](backend/app/schemas/question_bank.py); các workflow nằm trong [question_bank services](backend/app/services/question_bank/).

## Tất cả route frontend

Route động dùng dấu ngoặc vuông như cấu trúc Next.js. `page.tsx` có thể chỉ gọi component trang hoặc chuyển hướng; khi đó sửa component đích.

| Route | File | Đầu mối giao diện/API |
| --- | --- | --- |
| `/analytics/learning` | [frontend/app/analytics/learning/page.tsx](frontend/app/analytics/learning/page.tsx) | Báo cáo học tập; `/analytics` |
| `/ap-sync` | [frontend/app/ap-sync/page.tsx](frontend/app/ap-sync/page.tsx) | Danh mục/đồng bộ; `/academic` |
| `/audit` | [frontend/app/audit/page.tsx](frontend/app/audit/page.tsx) | Nhật ký hoạt động; `/audit` |
| `/auth/cms-callback` | [frontend/app/auth/cms-callback/page.tsx](frontend/app/auth/cms-callback/page.tsx) | AppContext, `/auth`, `/rbac/me` |
| `/auth/logged-out` | [frontend/app/auth/logged-out/page.tsx](frontend/app/auth/logged-out/page.tsx) | AppContext, `/auth`, `/rbac/me` |
| `/bank/chapters/[chapterId]` | [frontend/app/bank/chapters/[chapterId]/page.tsx](frontend/app/bank/chapters/[chapterId]/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/departments/[departmentId]/subjects` | [frontend/app/bank/departments/[departmentId]/subjects/page.tsx](frontend/app/bank/departments/[departmentId]/subjects/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/departments` | [frontend/app/bank/departments/page.tsx](frontend/app/bank/departments/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/history` | [frontend/app/bank/history/page.tsx](frontend/app/bank/history/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank` | [frontend/app/bank/page.tsx](frontend/app/bank/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/quiz` | [frontend/app/bank/quiz/page.tsx](frontend/app/bank/quiz/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/search` | [frontend/app/bank/search/page.tsx](frontend/app/bank/search/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/subject-versions/[versionId]/chapters` | [frontend/app/bank/subject-versions/[versionId]/chapters/page.tsx](frontend/app/bank/subject-versions/[versionId]/chapters/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/bank/subjects/[subjectId]/versions` | [frontend/app/bank/subjects/[subjectId]/versions/page.tsx](frontend/app/bank/subjects/[subjectId]/versions/page.tsx) | `bank/_components/pages` hoặc Quiz/Search; `/question-bank-v2` |
| `/dashboard` | [frontend/app/dashboard/page.tsx](frontend/app/dashboard/page.tsx) | Chuyển hướng đến `/bank` |
| `/export` | [frontend/app/export/page.tsx](frontend/app/export/page.tsx) | Chuyển hướng đến `/bank/quiz` |
| `/generate` | [frontend/app/generate/page.tsx](frontend/app/generate/page.tsx) | Chuyển hướng đến `/bank` |
| `/import-quiz-cms-old` | [frontend/app/import-quiz-cms-old/page.tsx](frontend/app/import-quiz-cms-old/page.tsx) | legacy_quiz_import; `/question-bank-v2` |
| `/jobs` | [frontend/app/jobs/page.tsx](frontend/app/jobs/page.tsx) | Tác vụ Bank/Academic, worker |
| `/ops/readiness` | [frontend/app/ops/readiness/page.tsx](frontend/app/ops/readiness/page.tsx) | Kiểm tra hệ thống; `/ops` |
| `/` | [frontend/app/page.tsx](frontend/app/page.tsx) | Xem component/chuyển hướng trong file |
| `/premises` | [frontend/app/premises/page.tsx](frontend/app/premises/page.tsx) | Danh mục/đồng bộ; `/academic` |
| `/question-bank` | [frontend/app/question-bank/page.tsx](frontend/app/question-bank/page.tsx) | Chuyển hướng đến `/bank` |
| `/review` | [frontend/app/review/page.tsx](frontend/app/review/page.tsx) | Chuyển hướng đến `/bank` |
| `/semesters` | [frontend/app/semesters/page.tsx](frontend/app/semesters/page.tsx) | Danh mục/đồng bộ; `/academic` |
| `/settings` | [frontend/app/settings/page.tsx](frontend/app/settings/page.tsx) | Cấu hình kỹ thuật; `/settings` |
| `/student-management/classes/[classId]` | [frontend/app/student-management/classes/[classId]/page.tsx](frontend/app/student-management/classes/[classId]/page.tsx) | StudentManagementPlatformPage / chi tiết lớp; `/academic` |
| `/student-management/cms` | [frontend/app/student-management/cms/page.tsx](frontend/app/student-management/cms/page.tsx) | StudentManagementPlatformPage / chi tiết lớp; `/academic` |
| `/student-management` | [frontend/app/student-management/page.tsx](frontend/app/student-management/page.tsx) | StudentManagementPlatformPage / chi tiết lớp; `/academic` |
| `/student-management/subjects/[subjectId]/classes` | [frontend/app/student-management/subjects/[subjectId]/classes/page.tsx](frontend/app/student-management/subjects/[subjectId]/classes/page.tsx) | StudentManagementPlatformPage / chi tiết lớp; `/academic` |
| `/student-management/udemy` | [frontend/app/student-management/udemy/page.tsx](frontend/app/student-management/udemy/page.tsx) | StudentManagementPlatformPage / chi tiết lớp; `/academic` |
| `/subject-management/[deliveryId]/udemy` | [frontend/app/subject-management/[deliveryId]/udemy/page.tsx](frontend/app/subject-management/[deliveryId]/udemy/page.tsx) | CMS/Udemy, kế hoạch; `/academic/subject-deliveries` |
| `/subject-management/[deliveryId]/udemy-plan` | [frontend/app/subject-management/[deliveryId]/udemy-plan/page.tsx](frontend/app/subject-management/[deliveryId]/udemy-plan/page.tsx) | CMS/Udemy, kế hoạch; `/academic/subject-deliveries` |
| `/subject-management` | [frontend/app/subject-management/page.tsx](frontend/app/subject-management/page.tsx) | CMS/Udemy, kế hoạch; `/academic/subject-deliveries` |
| `/sync` | [frontend/app/sync/page.tsx](frontend/app/sync/page.tsx) | Chuyển hướng đến `/ap-sync` |
| `/teacher-management/classes/[classId]` | [frontend/app/teacher-management/classes/[classId]/page.tsx](frontend/app/teacher-management/classes/[classId]/page.tsx) | TeacherManagementPlatformPage / chi tiết giảng viên; `/academic/training` |
| `/teacher-management/cms` | [frontend/app/teacher-management/cms/page.tsx](frontend/app/teacher-management/cms/page.tsx) | TeacherManagementPlatformPage / chi tiết giảng viên; `/academic/training` |
| `/teacher-management` | [frontend/app/teacher-management/page.tsx](frontend/app/teacher-management/page.tsx) | TeacherManagementPlatformPage / chi tiết giảng viên; `/academic/training` |
| `/teacher-management/teachers/[teacherId]/classes` | [frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx](frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx) | TeacherManagementPlatformPage / chi tiết giảng viên; `/academic/training` |
| `/teacher-management/udemy` | [frontend/app/teacher-management/udemy/page.tsx](frontend/app/teacher-management/udemy/page.tsx) | TeacherManagementPlatformPage / chi tiết giảng viên; `/academic/training` |
| `/training-management` | [frontend/app/training-management/page.tsx](frontend/app/training-management/page.tsx) | Xem component/chuyển hướng trong file |
| `/users` | [frontend/app/users/page.tsx](frontend/app/users/page.tsx) | BusinessRBACService; `/rbac` |
| `/workflow` | [frontend/app/workflow/page.tsx](frontend/app/workflow/page.tsx) | Chuyển hướng đến `/bank` |

## CSS và thành phần dùng chung

- Thứ tự tải CSS được khai báo tại [frontend/app/layout.tsx](frontend/app/layout.tsx). Nhiều stylesheet cũ dùng `!important`; cần kiểm tra selector đang thắng trước khi sửa.
- [globals.css](frontend/app/globals.css): nền toàn hệ thống. Không đặt bố cục riêng của Bank/Import/đào tạo vào đây. Đợt rà soát này không sửa file này.
- [project-spacing-contract.css](frontend/styles/project-spacing-contract.css): token và mặc định độ ưu tiên thấp `:where(...)`.
- [bank-design-contract.css](frontend/styles/bank-design-contract.css): Bank, ô tìm môn trong toolbar, hộp thoại Quiz; selector phải giữ scope trang/hộp thoại.
- [operations-catalog-rbac-ux.css](frontend/styles/operations-catalog-rbac-ux.css): bộ lọc, KPI, danh mục, phân quyền.
- [student-operations-visual-hotfix.css](frontend/styles/student-operations-visual-hotfix.css), [training-analytics-ux.css](frontend/styles/training-analytics-ux.css): trang lớp, sinh viên, giảng viên.
- [subject-management-udemy.css](frontend/styles/subject-management-udemy.css): quản lý môn, tiến độ/kế hoạch Udemy.
- [frontend-runtime-contracts.css](frontend/styles/frontend-runtime-contracts.css): dialog, thông báo, trạng thái route.
- Open edX đọc API dùng `OPENEDX_REQUEST_TIMEOUT_SECONDS` (30 giây mặc định); các lệnh ghi tạo Quiz/Final test/Problem Bank dùng `OPENEDX_WRITE_TIMEOUT_SECONDS` (180 giây mặc định).
- [global-workspace-scroll-notice-hotfix.css](frontend/styles/global-workspace-scroll-notice-hotfix.css): cuộn workspace, notice trong AppShell.
- [OperationsWorkspace.module.css](frontend/components/operations/OperationsWorkspace.module.css): khoảng cách giữa thông báo, bảng và nội dung bên trong từng WorkspaceSection.
- [FeedbackMessage.module.css](frontend/components/ui/FeedbackMessage.module.css): notice trong trang và portal dialog; không phụ thuộc vị trí bên trong AppShell.
- 44 vị trí thông báo legacy đã chuyển sang `ContentNotice`/`InlineNotice`/`ActionMessage` hoặc trạng thái bảng chuyên biệt. JSX không còn render `.alert`/`.form-message` cũ; các chuỗi `alert` còn lại là `role="alert"`, icon hoặc selector CSS tương thích.
- [Import page.module.css](frontend/app/import-quiz-cms-old/page.module.css): chỉ áp dụng Import Quiz CMS cũ.

`PageRoot` là fragment và đăng ký class cho `<main>` trong AppShell. Khi thêm/sửa một trang đào tạo phải giữ class nền và `training-operations-page`; không giả định class fallback của shell vẫn còn sau khi trang đăng ký. `AccessibleDialog` được render qua portal; selector chỉ nằm dưới class trang sẽ không áp dụng cho nội dung dialog. Dùng `className`/`bodyClassName` hoặc CSS module của component.

## Backend và dữ liệu

| Nhóm | Điểm vào | Logic/model |
| --- | --- | --- |
| API mount + lỗi | [main.py](backend/app/main.py), [api router](backend/app/api/router.py), [errors.py](backend/app/core/errors.py) | JSON lỗi giữ `code`, HTTP status, request ID; frontend hiển thị câu hướng dẫn |
| RBAC | [routes/rbac.py](backend/app/api/routes/rbac.py), [schemas/rbac.py](backend/app/schemas/rbac.py) | [models/rbac.py](backend/app/models/rbac.py), [business_rbac.py](backend/app/services/business_rbac.py) |
| AP + đào tạo | [routes/academic.py](backend/app/api/routes/academic.py), [schemas/academic.py](backend/app/schemas/academic.py) | [models/academic.py](backend/app/models/academic.py), [services/academic](backend/app/services/academic/) |
| Bank + Quiz | [routes/question_bank_v2.py](backend/app/api/routes/question_bank_v2.py) | [question_bank_service](backend/app/services/question_bank_service.py), [workflow modules](backend/app/services/question_bank/) |
| Tác vụ | [worker.py](backend/app/worker.py) | [job model](backend/app/models/job.py), tác vụ academic/bank trong model tương ứng |
| Open edX | [openedx_client.py](backend/app/services/openedx_client.py) | [connector plugin](openedx-connector-plugin/), [unit reset plugin](openedx-unit-reset-plugin/) |
| Cấu hình | [core/config.py](backend/app/core/config.py) | Biến môi trường runtime; không ghi khóa hoặc token vào tài liệu/chỉ mục |

AP client gửi `product=POLY|PTCD`; `get-all-subject` gửi `term_name` theo học kỳ. URL thực tế có thể bị ENV ghi đè, cần đối chiếu cấu hình đang chạy khi kiểm tra production.

## Kiểm tra khi sửa tiếp

Các lệnh dưới đây chạy từ thư mục gốc, sau khi đã cài dependencies:

```bash
git status --short
git diff --stat
git diff --check
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
node --test frontend/tests/user-facing-errors.test.cjs
```

Từ thư mục `backend`, dùng Python của virtualenv đã cài `requirements-ci.txt`:

```bash
python -m pytest app/tests/test_rbac_admin_campus_owner_contract.py app/tests/test_public_validation_messages.py app/tests/test_legacy_quiz_cms_old_import.py app/tests/test_academic_ap_internal_api.py app/tests/test_academic_connector_contract_compat.py app/tests/test_auth_callback_rbac_refresh_contract.py -q
```

- Test RBAC dùng DB SQLite và HTTP: admin được cấp/thu hồi, chủ cơ sở toàn hệ thống, cấm tự nâng quyền, cấp/thu hồi từng cơ sở, CRUD học kỳ.
- Test thông báo frontend dùng module thật: HTTP envelope, validation tiếng Việt, lỗi tác vụ, giữ diagnostic riêng.
- [e2e/tests](e2e/tests/): shell/bank, quản lý môn, Udemy; cần trình duyệt và server chạy được. Đợt rà soát 06/09/2026 chưa chạy được kiểm tra hình ảnh/E2E vì trình duyệt bị chặn truy cập local. Chưa xác nhận không chồng lấn trên mọi kích thước màn hình hoặc trên production.
- Nhiều test `test_v25_*` là snapshot phiên bản/lịch sử. Khi chạy chúng cần phân biệt assertion phiên bản cũ với regression hành vi; không sửa số phiên bản/fixture hàng loạt để che test lỗi.

Khi thay đổi route, quyền hoặc vị trí workflow, cập nhật chỉ mục này trong cùng thay đổi.
