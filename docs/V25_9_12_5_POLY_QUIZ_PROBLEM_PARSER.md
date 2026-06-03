# v25.9.12.5 - Poly Quiz Problem Parser Fix

## Vấn đề

Một số quiz cũ trong CMS lưu nhiều câu hỏi trong một `problem` XML theo cấu trúc custom:

- Câu hỏi nằm trong `div.poly` / `pre.poly-body`
- Đáp án nằm trong `multiplechoiceresponse` ngay sau đó
- `multiplechoiceresponse` không có thẻ `label`

Parser cũ chỉ đọc câu hỏi nằm trong `label` bên trong `multiplechoiceresponse`, nên các quiz kiểu này bị fallback sang plain text. Kết quả là Node Detail hiển thị thành một đoạn dài và mất marker đáp án đúng. Các câu PRF vẫn chạy vì PRF có `label` chuẩn trong `multiplechoiceresponse`.

## Sửa đổi

- `backend/app/services/problem_parser.py`
  - Thêm parser cho cấu trúc `div.poly` + `pre.poly-body` đứng trước `multiplechoiceresponse`.
  - Mỗi `multiplechoiceresponse` được coi là một câu hỏi riêng.
  - Không parse trùng `choicegroup` khi đã parse `multiplechoiceresponse`.
  - Giữ `correct="true"` và render `[ĐÁP ÁN ĐÚNG]` cho teacher/admin UI.
  - Bỏ metadata `{"filename": [...]}` khỏi content.

- `frontend/app/sync/page.tsx`
  - Cập nhật notice: problem/quiz cũ được phép dùng làm nguồn trong phạm vi chọn, nhưng AI phải đổi cách hỏi và không copy nguyên văn.

- `backend/app/tests/test_v25_9_regression.py`
  - Thêm regression test cho quiz kiểu Poly/FPT.
  - Cập nhật test policy: problem chunks được phép làm source để rewrite.

## Kết quả mong đợi

Node `Trắc nghiệm cuối bài` sẽ hiển thị dạng:

```txt
[SOURCE TYPE: EXISTING OPEN EDX PROBLEM]
...
CÂU 1: Website được xây dựng trên một hay nhiều ngôn ngữ lập trình ?
A. Một và chỉ một ngôn ngữ duy nhất
B. Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau [ĐÁP ÁN ĐÚNG]
C. Có thể xây dựng website bằng 2 ngôn ngữ lập trình
D. Không cần ngôn ngữ lập trình nào cũng có thể xây dựng website
```

Khi generate từ quiz cũ, AI được dùng quiz cũ làm nguồn kiến thức nhưng phải tạo câu hỏi mới bằng cách hỏi khác.
