# v24.4 - Question Card UI

## Mục tiêu

Giảm nhiễu trong màn hình Question Bank / Teacher Review / Workflow Review. Danh sách câu hỏi không còn hiển thị Meta và Source ở bên ngoài.

## Thay đổi UI

Mỗi câu hỏi được hiển thị thành 3 ô:

1. **Câu hỏi + đáp án**
   - Phần trên là nội dung câu hỏi.
   - Phần dưới là 4 đáp án A/B/C/D.
   - Đáp án đúng được tô xanh.

2. **Status**
   - Chỉ hiển thị trạng thái hiện tại của câu hỏi.

3. **Action**
   - Edit / Approve / Reject / Publish / Undo / OLX tùy trạng thái và quyền.

## Ẩn khỏi danh sách ngoài

Các phần sau không còn hiện trực tiếp trong list:

- Meta
- Source
- source_node_id
- source_ref
- source_excerpt
- chapter/library metadata
- quality/version
- learning objective/explanation

Những dữ liệu này vẫn được giữ trong database và vẫn dùng cho export/publish/filter/internal logic. Khi cần sửa chi tiết, giáo viên bấm **Edit** để mở popup.

## File đã sửa

- `frontend/components/questions/QuestionTable.tsx`
- `frontend/app/globals.css`
