# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.13

## Baseline

```text
v25.9.16.7.2.64.13 — Enterprise Navigation + DataTable UX Foundation
zip: ai-server-openedx-v25.9.16.7.2.64.13-enterprise-navigation-datatable-ux-foundation.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.12` tiếp tục từ `.64.11`. Không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Bank hierarchy bắt buộc

```text
Bộ môn → Môn học → Phiên bản môn theo học kỳ → Bài/Chapter → Câu hỏi
```

Quy tắc:

- Mỗi môn chỉ có một phiên bản môn cuối trong một học kỳ.
- Backend chặn tạo hoặc đổi phiên bản môn sang học kỳ đã có phiên bản.
- Release là snapshot/chốt bộ đề của Chapter, không phải node trong cây.
- Quiz/Final test là workflow đầu ra sau Bank, không phải node trong cây.
- Độ khó là thuộc tính/bộ lọc của câu hỏi, không phải cấp thư mục.

## Thay đổi `.64.12`

### Sidebar/IA

Sidebar được chia thành:

```text
Tổng quan
Ngân hàng câu hỏi
Đào tạo
Vận hành & quản trị
```

Menu Bank ghi rõ hierarchy 5 cấp. `Tạo Quiz từ bộ đề` và `Lịch sử Quiz` là chức năng cùng nhóm Bank nhưng nằm ngoài cây hierarchy.

### Shared Breadcrumbs

Thêm:

```text
frontend/components/navigation/Breadcrumbs.tsx
```

Bank pages dùng component này thông qua `frontend/app/bank/_components/shared.tsx`. Student-management topbar cũng dùng component chung.

### Enterprise DataTable foundation

Thêm:

```text
frontend/components/table/EnterpriseDataTable.tsx
frontend/components/table/TableStates.tsx
frontend/hooks/useUrlTableState.ts
frontend/styles/enterprise-ui.css
```

Hỗ trợ:

```text
compact / standard / comfortable density
sticky header
sticky left/right columns
horizontal scroll trong container riêng
column visibility lưu localStorage
page/page_size/density/search/status lưu URL
20/50/100 dòng mỗi trang
empty/loading/error states
row selection contract + chọn tất cả trên trang
```

Màn áp dụng đầu tiên:

```text
/bank/departments
```

URL hỗ trợ:

```text
q
status
page
page_size
density
sort (contract đã có; từng màn sẽ nối server-side sort sau)
```

### One version per term

`VersionedQuestionBankService.create_subject_offering()` và `update_subject_offering()` chặn trùng `subject_id + term` bằng thông báo:

```text
Mỗi học kỳ chỉ có một phiên bản môn cuối.
```

Không thêm DB migration ở bản này; constraint service bổ sung trên nền unique code hiện có. Nếu production có concurrent create cao, cân nhắc migration unique `(subject_id, term)` sau khi dọn dữ liệu trùng và audit UAT.

## Kiểm tra đã chạy

```text
v64.12-specific tests: 6 passed
selected non-doc v64.10-v64.12 regression: 15 passed, 3 stale doc/version tests deselected
backend compileall: passed
frontend npm ci: passed
frontend typecheck: passed
frontend Next production build: compiled, typechecked và generated 29/29 static pages; command bị timeout tại Collecting build traces dù .next/BUILD_ID đã được tạo
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN, failures=0, warnings=4, passes=31
```

Build-gate warnings chỉ do sandbox gate không thấy backend deps/psycopg trong interpreter gate, RUN_FRONTEND_BUILD=0, Docker/.env.production không có và RUN_REVIEW_PACK=0. Frontend typecheck đã được chạy riêng thành công.

## Kế hoạch tối ưu còn lại

### `.64.13 — Bank Workflow UX Completion`

Áp dụng trên đúng cây 5 cấp, không thêm Release/Quiz làm hierarchy:

```text
- Migrate Môn, Phiên bản môn, Bài và Câu hỏi sang EnterpriseDataTable.
- Server-side search/filter/sort/pagination cho question list.
- Batch actions: duyệt, bỏ duyệt, đổi độ khó, đổi concept, chuyển bài, thêm vào release.
- Phân biệt chọn trang hiện tại và chọn toàn bộ kết quả lọc.
- Preview Question trong Chapter workspace.
- Preview Release là snapshot đóng băng, mở từ Chapter/Release action.
- Preview Quiz mở từ Tạo Quiz, không nằm trong cây Bank.
- Import câu hỏi: upload → validate → preview → confirm → worker job → error workbook.
- Export selected/current filter/all filtered.
- Confirmation modal cho delete/publish/rollback/import overwrite.
```

### `.64.14 — Training/Ops UX Completion + Acceptance Gate`

```text
- Migrate teacher/student/analytics/jobs/audit sang EnterpriseDataTable.
- URL filters, sticky identity/action columns, export theo filter.
- Semantic status có màu + icon + text.
- Progress bars cho duyệt/release/sync/tiến độ học.
- Hoàn thiện compact ops readiness.
- Thêm read-only UX acceptance gate và script UAT.
- Không khôi phục luồng ghi điểm Assignment; Assignment vẫn externalized.
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-enterprise-navigation-datatable-ux-foundation.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```
