# v25.9.15.6.6 - Bank Review UI + Release Guard Hotfix

## Lý do

UI danh sách câu hỏi trong chapter workspace chưa giống trang `/review`, thiếu đáp án A/B/C/D và thao tác duyệt/bỏ chưa rõ. Ngoài ra điều kiện chốt bộ đề phải chặt hơn: chỉ khi toàn bộ câu hỏi đã được giáo viên xử lý xong mới được chốt Release.

## Thay đổi

### Frontend

- `/bank/chapters/{chapterId}` dùng layout thẻ câu hỏi giống trang `/review`.
- Mỗi câu hiển thị đủ đáp án A/B/C/D, đáp án đúng được highlight.
- Hiển thị trạng thái, độ khó, concept, family, variant, điểm chất lượng.
- Câu lỗi hiển thị lý do lỗi và nút `Bỏ câu lỗi`.
- Nếu còn câu chưa xử lý, nút `Chốt bộ đề` bị khóa và hiện cảnh báo.

### Backend

- `BankVersionQuestionOut` trả thêm option A/B/C/D, explanation, concept, source, quality/draft error để frontend hiển thị như review.
- `release_readiness` coi `draft_error` là lỗi chặn release, không còn là warning.
- Release chỉ được tạo khi không còn `pending_review`, `needs_review`, `draft_error`.
- Quota 100 câu/chapter tính theo tổng câu đã tạo chưa retired, kể cả câu rejected/draft_error, để tránh vượt chỉ tiêu bằng cách bỏ câu rồi tạo thêm vô hạn.

## Nguyên tắc nghiệp vụ

```text
Chốt bộ đề = chỉ được làm sau khi giáo viên xử lý xong tất cả câu hỏi.

Câu được tính là đã xử lý:
- approved
- published
- rejected

Câu chưa xử lý:
- pending_review
- needs_review
- draft_error
```
