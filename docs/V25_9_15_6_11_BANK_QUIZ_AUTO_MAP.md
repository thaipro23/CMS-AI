# v25.9.15.6.11 - Bank Quiz Auto Map by Course ID

## Mục tiêu

Trang `/bank/quiz` không còn bắt giáo viên tự chọn Bộ môn → Môn → Version → Bài → Release → Node Open edX.

Luồng mới:

```text
Dán Course ID
→ hệ thống tự tìm môn từ mã course
→ hệ thống tự tìm version môn phù hợp với run/kỳ
→ chỉ chọn version đã có Release published cho tất cả bài
→ đọc Section trong Open edX course
→ tự map Section vào Bài cùng tên
→ giáo viên xác nhận lưu mapping
→ tạo Quiz từng bài hoặc tạo tất cả
```

## API mới

```http
POST /api/question-bank-v2/quiz/auto-map/preview
POST /api/question-bank-v2/quiz/auto-map/apply
```

Payload:

```json
{
  "openedx_course_id": "course-v1:FPT+WEB107+SU25",
  "total_questions": 15,
  "difficulty_easy": 50,
  "difficulty_medium": 30,
  "difficulty_hard": 20,
  "max_families_per_bank": 2
}
```

## Rule tự tìm version

Course ID `course-v1:FPT+WEB107+SU25` sẽ được hiểu là:

```text
Môn: WEB107
Kỳ/run: SU25
```

Backend tìm `Subject.code = WEB107`, sau đó tìm `SubjectOffering` phù hợp như `WEB107_SU25`, `term=SU25`, hoặc code có chứa `SU25`.

Version chỉ được coi là sẵn sàng nếu tất cả chapter active trong version đó có Release `published` và mỗi Release có Open edX Library component đầy đủ.

## Rule tự map Section

Backend đọc cây course từ Open edX connector. Ưu tiên block type `chapter` vì đây là Section trong Studio. Nếu không có chapter thì fallback sang `sequential` và trả cảnh báo.

Map theo:

```text
Tên Bài trong ngân hàng == Tên Section trong Open edX
```

Hoặc cùng số bài, ví dụ:

```text
Bài 1 ↔ Bài 1
Bài 1.1 ↔ Bài 1.1
```

## Không thêm migration

Bản này dùng lại bảng hiện có:

```text
ai_edx_course_mappings
ai_edx_course_chapter_mappings
ai_course_quiz_instances
```

