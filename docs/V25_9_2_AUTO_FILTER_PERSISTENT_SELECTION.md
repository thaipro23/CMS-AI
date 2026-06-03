# v25.9.2 - Auto Filter Loading + Persistent Selection

## Mục tiêu

Bản này sửa UX filter theo yêu cầu mới: người dùng chọn filter là hệ thống tự tải lại, không cần bấm Apply filters, nhưng selection đang tick không bị mất.

## Thay đổi chính

- Question Bank bỏ nút Apply filters.
- Question Bank tự load khi đổi Status, Difficulty, Source type, Source node, Search hoặc Sort.
- Search được debounce ngắn để tránh gọi API quá dày khi người dùng đang gõ.
- Generate page bỏ Apply filters cho chunk browser.
- Workflow Select step bỏ Apply filters cho chunk browser.
- Reset filters chỉ reset điều kiện lọc, không clear selection.
- Clear selected mới xóa các item đã tick.
- Selection lưu theo ID, không theo index, nên đổi filter không làm mất tick.
- UI hiển thị số item đang được chọn nhưng bị ẩn bởi filter.
- Khi filter đang load, UI hiển thị spinner/soft tag để người dùng biết hệ thống đang tải.

## Quy tắc selection

Selection chỉ bị clear khi:

- Người dùng bấm Clear selected.
- Người dùng đổi sang course khác.
- Item bị delete thành công.
- Workflow reset hoàn toàn nếu sau này thêm nút reset workflow.

Selection không bị clear khi:

- Đổi status filter.
- Đổi difficulty filter.
- Đổi source type.
- Đổi node filter.
- Gõ search.
- Sort lại danh sách.
- Bấm Reset filters.

## File frontend đã sửa

- `frontend/components/questions/QuestionFilters.tsx`
- `frontend/app/question-bank/page.tsx`
- `frontend/app/generate/page.tsx`
- `frontend/app/workflow/page.tsx`
- `frontend/app/globals.css`

## Kiểm tra

Đã chạy:

```bash
cd frontend
npm run build
```

Kết quả: Next.js compiled successfully và generate static pages OK.
