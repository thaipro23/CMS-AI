# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Bank Workflow UX Completion
zip: ai-server-openedx-v25.9.16.7.2.64.13-bank-workflow-ux-completion.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.13` tiếp tục từ `.64.12`. Không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Cây Bank chuẩn bắt buộc

```text
Bộ môn
→ Môn học
→ một Phiên bản môn cuối theo học kỳ
→ Bài/Chapter
→ Câu hỏi
```

Release và Quiz là workflow đầu ra, không phải node hierarchy:

```text
Câu hỏi đã duyệt trong Chapter
→ chốt Release
→ publish Open edX Library
→ tạo Quiz/Final test
```

Mỗi môn trong một học kỳ chỉ có một Subject Offering/Phiên bản môn cuối. Backend `.64.12+` chặn duplicate `subject_id + term` với thông báo `Mỗi học kỳ chỉ có một phiên bản môn cuối.`

## Thay đổi chính `.64.13`

### Enterprise tables cho hierarchy

Các màn sau dùng `EnterpriseDataTable` và URL table state:

```text
frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx
frontend/app/bank/_components/pages/SubjectVersionsPage.tsx
frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx
frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx
```

Hỗ trợ:

```text
q/status/difficulty/sort/page/page_size/density trong URL
20/50/100 dòng mỗi trang
sticky header
sticky STT/entity/action columns
column visibility preference
compact/standard/comfortable density
empty/loading/error states
horizontal scroll trong container riêng
```

### Question table server-side

Endpoint mới:

```text
GET /api/question-bank-v2/bank-versions/{bank_version_id}/questions/page
```

Filter/sort:

```text
status_filter
difficulty
search
sort = needs_review | newest | oldest | difficulty | quality_low | quality_high
page
page_size <= 100
```

Frontend:

```text
frontend/hooks/useBankQuestionTableState.ts
frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx
```

Search debounce 350 ms, không gọi API ngay theo từng phím gõ.

### Selection và batch review

Phân biệt rõ:

```text
Chọn tất cả bản ghi trên trang
Chọn toàn bộ kết quả đang lọc
```

`BankQuestionBulkReviewRequest` hỗ trợ:

```text
question_ids
apply_to_filtered
status_filter
difficulty
search
```

Filtered synchronous batch có cap 2.000 câu để tránh HTTP request quá nặng. Published questions luôn bị bỏ qua. Bulk reject có confirmation dialog.

### Question preview

Question preview hiển thị:

```text
status
difficulty
quality score
question text
A/B/C/D
correct answer
concept/family
explanation
source evidence
draft error reason
```

### Frozen Release membership preview

Endpoint mới:

```text
GET /api/question-bank-v2/releases/{release_id}/preview
```

Dữ liệu membership lấy từ:

```text
ai_bank_release_questions
```

Không lấy danh sách theo filter câu hỏi hiện tại. Nội dung câu được lấy từ linked question trong Bank Version đã khóa sau Release/publish.

Frontend có nút:

```text
Xem trước Release
```

### Import Excel an toàn

Backend module mới:

```text
backend/app/services/question_bank/import_export.py
```

Endpoints:

```text
GET  /bank-versions/{id}/questions/import-template.xlsx
POST /bank-versions/{id}/questions/import-preview
GET  /bank-versions/{id}/questions/import-errors/{preview_token}.xlsx
POST /bank-versions/{id}/questions/import-job
```

Flow:

```text
Tải template
→ chọn .xlsx
→ validate toàn file
→ preview tối đa 20 dòng + lỗi tối đa 100 dòng
→ tải bank-question-import-errors.xlsx nếu lỗi
→ chỉ khi 0 dòng lỗi mới xác nhận
→ tạo Celery job bank_question_import_task
→ câu mới ở pending_review
```

Giới hạn/safety:

```text
file <= 10 MB
max 2.000 data rows
zip/OpenXML member count <= 500
uncompressed size <= 40 MB
reject unsafe archive paths
strict required headers
strict difficulty easy/medium/hard
strict correct_answer A/B/C/D
reject duplicate options
reject duplicate questions in file
preview token 32 hex chars
preview owner must match user
preview expires after 2 hours
```

Import không tự approve, không tạo Release và không publish.

### Export CSV

Endpoint:

```text
GET /bank-versions/{id}/questions/export.csv
```

Hỗ trợ:

```text
current filter
selected question_ids
all filtered (cap 50.000 rows)
UTF-8 BOM để mở Excel tiếng Việt
```

### Confirmation dialogs

Đã thêm confirmation cho:

```text
bulk reject
chốt Release
publish Release lên CMS/Open edX
```

## Các file chính

```text
backend/app/services/question_bank/import_export.py
backend/app/api/routes/question_bank_v2.py
backend/app/schemas/question_bank.py
backend/app/worker.py
frontend/components/table/EnterpriseDataTable.tsx
frontend/hooks/useUrlTableState.ts
frontend/hooks/useBankQuestionTableState.ts
frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx
frontend/app/bank/_components/BankQuestionImportModal.tsx
frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx
frontend/app/bank/_components/pages/SubjectVersionsPage.tsx
frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx
frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx
frontend/styles/enterprise-ui.css
```

## Quy tắc giữ nguyên

```text
Không fake dữ liệu.
Không reset DB/xóa volume/sửa tay alembic_version.
Không docker compose down -v.
Tác vụ nặng phải chạy worker/job nền.
Backend enforce RBAC.
Không dùng wording kết luận gian lận/vi phạm.
Assignment score write đã externalized, không khôi phục.
Release và Quiz không phải node hierarchy.
```

## Kết quả kiểm tra artifact

```text
v64.13 + v64.12 tests: 14 passed
selected Bank/security/workflow regression: 43 passed
backend compileall: passed
frontend typecheck: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0, passes=24
uat-build-gate sandbox: WARN, failures=0, warnings=4, passes=31
```

Frontend production build:

```text
Compiled successfully
Type validation successful
Generated static pages 29/29
Reached Finalizing page optimization / Collecting build traces
```

Trong sandbox, command vẫn timeout ở `Collecting build traces` dù compile/typecheck/static generation hoàn tất. Cần chạy lại full Docker/Next build trên UAT để chốt standalone trace.

`npm ci` báo 2 dependency vulnerabilities hiện hữu (1 moderate, 1 high). Không chạy `npm audit fix --force` tự động vì có thể nâng Next.js breaking; cần review dependency riêng.

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-bank-workflow-ux-completion.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## UAT verify quan trọng

```text
1. Đi cây Bank từ Bộ môn đến Câu hỏi.
2. Xác nhận một môn không tạo được hai phiên bản cùng học kỳ.
3. Filter/search/page/density giữ sau F5.
4. Checkbox header chỉ chọn trang hiện tại.
5. “Chọn toàn bộ kết quả lọc” hiển thị scope rõ.
6. Import file đúng và sai; tải error workbook.
7. Worker import hoàn tất và câu mới pending_review.
8. Preview Question và Release đúng.
9. Chốt/publish/bulk reject có confirm.
10. Không xuất hiện lại Workflow Assignment score.
```

## Bản tiếp theo theo kế hoạch

```text
v25.9.16.7.2.64.14 — Training/Ops UX Completion + UAT UX Acceptance Gate
```
