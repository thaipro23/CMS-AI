# v25.9.15.6.14 - Bank Quiz Timer UI + FPT Naming/Grading Hotfix

## Mục tiêu

Sửa trang `/bank/quiz` theo quy định FPT khi tạo Quiz tự luyện từ Bank Release.

## Thay đổi chính

### 1. Hiển thị cấu hình timer trong `/bank/quiz`

Trang tạo Quiz có thêm phần:

- Bật timer
- Thời gian làm bài/phút
- Thời gian chờ làm lại/phút
- Tự nộp các câu đã chọn khi hết giờ
- Khóa submit sau khi hết giờ

Timer vẫn là custom timer, không dùng native Timed Exam của Open edX.

### 2. Quy định đặt tên FPT

Nếu Section/Bài trong course là:

```text
Bài 1
Bài 2
Bài 1.1
Bài 1.2
```

thì AI Server tạo Subsection Quiz là:

```text
Quiz 1
Quiz 2
Quiz 1.1
Quiz 1.2
```

Unit bên trong luôn tên:

```text
Quiz
```

### 3. Grade as = Quiz

Connector tạo/ cập nhật Subsection với:

```text
format = Quiz
graded = true
```

Như vậy trong Studio phần Subsection sẽ được gắn `Grade as: Quiz` theo quy định FPT.

### 4. Backend enforce rule

Backend không còn tin hoàn toàn vào `quiz_title`/`unit_title` frontend gửi lên. Khi tạo quiz từ release, backend tự suy ra tên từ Chapter:

```text
Chapter Bài 1 -> quiz_title = Quiz 1
unit_title = Quiz
```

Điều này tránh frontend cũ tạo nhầm tên `AI Learning Check` hoặc `Quiz tự luyện`.

## File sửa

```text
frontend/app/bank/quiz/page.tsx
backend/app/services/question_bank_service.py
backend/app/schemas/question_bank.py
openedx-connector-plugin/openedx_ai_connector/views.py
```
