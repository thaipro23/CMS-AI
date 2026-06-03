# v25.9.12.4 - Problem Rewrite Source Policy

Bản này chỉnh logic theo yêu cầu: câu hỏi cũ trong CMS vẫn được dùng làm tài liệu nguồn, nhưng AI phải tạo câu hỏi Learning Check mới bằng cách hỏi khác.

## Thay đổi chính

- Cho phép `source_type=problem` tham gia prompt khi nằm trong phạm vi node/chapter/course được giáo viên chọn.
- Prompt nêu rõ: được dùng quiz cũ để hiểu kiến thức chuẩn và đáp án đúng, nhưng không copy nguyên văn câu hỏi cũ.
- Với problem source, prompt yêu cầu đổi cách diễn đạt, đổi góc hỏi hoặc đặt tình huống học tập đơn giản.
- Quality checker chặn câu sinh ra quá giống câu hỏi cũ bằng `old_problem_copy`.
- Node Detail vẫn hiển thị đáp án đúng cho teacher/admin để kiểm tra nguồn.

## File đã sửa

- `backend/app/services/prompt_builder.py`
- `backend/app/services/generation_planner.py`
- `backend/app/services/quality_checker.py`
- `backend/app/services/problem_parser.py`

## Ý nghĩa

Hệ thống không bỏ phí quiz/problem cũ. Các câu hỏi cũ trở thành nguồn tri thức để AI hiểu trọng tâm bài học, nhưng output không được là bản copy. Nếu model trả câu hỏi quá giống câu cũ, câu đó sẽ bị đưa về `draft_error` với lý do rõ ràng để giáo viên repair.
