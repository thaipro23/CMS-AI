# v25.9.15.5 - Create Quiz from Bank Release + Native ItemBank

## Mục tiêu

Khép kín luồng Question Bank First:

```text
Bank Release đã published sang Open edX Library
→ mapping course/chapter an toàn
→ lập Family Slot Plan từ release
→ tạo Quiz node thật trong Open edX Studio
→ tạo native Problem Bank Beta / itembank cho từng slot
→ verify kết quả từ Open edX connector
```

## API mới

### Preview kế hoạch Quiz

```http
POST /api/question-bank-v2/releases/{release_id}/quiz/preview
```

Payload:

```json
{
  "total_questions": 15,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20,
  "max_families_per_bank": 2
}
```

API này không gọi GPT. Nó dùng các câu đã nằm trong Bank Release, đã có `openedx_library_problem_id`, rồi gom deterministic theo difficulty + family. Một câu/component không được xuất hiện ở nhiều slot.

### Tạo Quiz thật trên Open edX

```http
POST /api/question-bank-v2/releases/{release_id}/quiz/create
```

Payload:

```json
{
  "course_chapter_mapping_id": "...",
  "quiz_title": "AI Learning Check - Bài 4",
  "unit_title": "Quiz tự luyện",
  "total_questions": 15,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20,
  "max_families_per_bank": 2
}
```

Điều kiện bắt buộc:

```text
Release.status = published
Release có openedx_library_key
Mỗi BankReleaseQuestion có openedx_library_problem_id
Course/chapter mapping pass guard
Open edX connector không được trả stub
```

## UI

Trang `/bank/quiz` đã mở nút:

```text
Xem kế hoạch
Tạo Quiz thật trên Open edX
```

Nút tạo Quiz chỉ hoạt động khi release đã published và mapping/chapter mapping an toàn.

## Native ItemBank

Luồng tạo dùng connector hiện có:

```text
connector.create_quiz_node(...)
connector.insert_problem_banks(...)
```

`insert_problem_banks` tạo `itembank`, không tạo `library_content`.

## Hạn chế trung thực

Nếu tạo Quiz node thành công nhưng insert Problem Bank thất bại, AI Server sẽ ghi `CourseQuizInstance.status = failed` và trả lỗi. Bản này chưa có endpoint delete/rollback Quiz node trong CMS connector, nên cần kiểm tra/xóa thủ công node lỗi trong Studio nếu lỗi xảy ra sau bước tạo node.

## Test đã chạy trong môi trường artifact

```text
python3 -m compileall backend/app backend/alembic: PASS
npm ci: PASS
tsc --noEmit: PASS
next build: compiled successfully nhưng timeout ở bước cuối environment artifact
pytest: chưa chạy được vì thiếu sqlalchemy trong môi trường ngoài container
```

Cần test thật trên server:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

Sau đó vào `/bank/quiz`, chọn release đã publish, validate mapping, bấm tạo Quiz thật.
