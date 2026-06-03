# v25.9.1 - Frontend UX Hotfix

## Mục tiêu

Bản này sửa các vấn đề UI người dùng cuối:

- Không hiện JSON thô trong các thông báo thông thường.
- Thông báo chuyển sang dạng notice: success / warning / error / info.
- Thêm Reset filters.
- Filter chỉ chạy khi bấm Apply filters, không auto load khi đang chọn.
- Khi Apply filters, các item đã tick không bị reset tùy tiện; chỉ loại bỏ selected ID không còn trong danh sách review.
- Các action button có loading state để người dùng biết hệ thống đang xử lý.
- Diversity report hiển thị dạng card dễ đọc thay vì JSON.
- Estimate cost hiển thị dạng summary card thay vì JSON.

## File chính đã sửa/thêm

Frontend:

- `frontend/components/ui/ActionMessage.tsx`
- `frontend/components/ui/LoadingButton.tsx`
- `frontend/components/ui/CostEstimateSummary.tsx`
- `frontend/components/questions/DiversityReportPanel.tsx`
- `frontend/components/questions/QuestionFilters.tsx`
- `frontend/components/questions/QuestionTable.tsx`
- `frontend/app/question-bank/page.tsx`
- `frontend/app/review/page.tsx`
- `frontend/app/workflow/page.tsx`
- `frontend/app/generate/page.tsx`
- `frontend/app/sync/page.tsx`
- `frontend/app/export/page.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/app/jobs/page.tsx`
- `frontend/app/dashboard/page.tsx`
- `frontend/app/users/page.tsx`
- `frontend/lib/api.ts`
- `frontend/app/globals.css`

## Kiểm tra

Đã chạy `npm run build` trong frontend. Kết quả phần compile/type check đã pass; command timeout ở bước cuối build trace trong sandbox nhưng Next.js đã báo `Compiled successfully` và đã generate static pages.

## Chạy lại

```bat
docker compose down
docker compose up --build
```

Nếu cần reset DB demo:

```bat
docker compose down -v
docker compose up --build
```
