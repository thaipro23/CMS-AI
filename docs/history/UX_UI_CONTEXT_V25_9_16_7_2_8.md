# UX/UI Context v25.9.16.7.2.8 — Flexible Bank Quiz Scope

## Nguyên tắc UX

`/bank/quiz` không được ép mọi chapter phải tạo Quiz. Người dùng phải nhìn vào một bảng và hiểu ngay bài nào tạo Quiz, bài nào bỏ qua, bài nào là Assignment/nội dung, bài nào là Final test.

## Wording chuẩn

Dùng các nhãn hành động:

- `Tạo Quiz`
- `Không tạo quiz`
- `Assignment/nội dung`
- `Tạo Final test`

Không dùng wording gây hiểu nhầm rằng version chưa hoàn thiện thì không thể map course. Version có thể được chọn nếu chỉ một phần chapter cần tạo assessment.

## Hành vi UI

- Version dropdown không disable version chỉ vì chưa phải mọi chapter đều có Release publish.
- Bảng chapter có cột `Tạo gì` để chọn hành động từng dòng.
- Dòng `Assignment/nội dung` và `Không tạo quiz` hiển thị trạng thái bỏ qua, không báo lỗi thiếu Release.
- Dòng `Tạo Quiz` và `Tạo Final test` vẫn phải hiển thị rõ nếu thiếu Section mapping hoặc Release publish.
- Modal tạo bài có hai khối cấu hình tách biệt:
  - `Cấu hình Quiz`
  - `Cấu hình Final test`
- Lịch sử tạo bài hiển thị loại `Quiz` hoặc `Final test` theo `metadata_json.assessment_type`.

## Cấu hình mặc định

Quiz:

- 15 câu
- EASY/MEDIUM/HARD = 50/30/20
- 15 phút
- cooldown 5 phút

Final test:

- 30 câu
- EASY/MEDIUM/HARD = 20/40/40
- 60 phút
- cooldown 0 phút

## Backend contract mới

`QuizAutoMapRequest` hỗ trợ:

```json
{
  "openedx_course_id": "course-v1:FPT+WEB107+SU26",
  "selected_subject_offering_id": "...",
  "chapter_plan": [
    { "chapter_id": "...", "action": "quiz" },
    { "chapter_id": "...", "action": "assignment" },
    { "chapter_id": "...", "action": "final_test" },
    { "chapter_id": "...", "action": "skip" }
  ]
}
```

`BankReleaseQuizCreateRequest` hỗ trợ:

```json
{
  "assessment_type": "quiz"
}
```

hoặc:

```json
{
  "assessment_type": "final_test"
}
```

## Không thay đổi

- Không đổi nguyên tắc Review Gate của Bank Release.
- Không tự tạo Release cho chapter chưa publish.
- Không tạo mapping Open edX cho dòng đã chọn bỏ qua.
- Không có migration.
