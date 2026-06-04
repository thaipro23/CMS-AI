# v25.9.14.1 - Question Family ID

## Mục tiêu

Bản này thêm lớp `question_family_id` để gom các câu hỏi cùng gốc nội dung/cùng concept+difficulty. Đây là nền tảng cho các bản sau tạo Balanced Problem Bank và chặn random trùng concept trong cùng một lượt học.

## Thay đổi chính

- Thêm `question_family_id`, `variant_no`, `source_evidence` vào `ai_questions`.
- Prompt JSON schema yêu cầu model trả về `question_family_id`, `variant_no`, `source_evidence`.
- Nếu model không trả family, backend tự sinh family ổn định từ `concept_key/concept_title + difficulty`.
- Review UI hiển thị Concept, Family và Variant trên từng câu.
- Form sửa câu hỏi cho phép chỉnh family/variant/evidence khi giáo viên cần gộp hoặc tách family thủ công.

## Quy tắc family

Mặc định:

```txt
1 concept + 1 difficulty = 1 question_family_id
```

Ví dụ:

```txt
mul211-vector-raster-easy
```

Các câu cùng kiểm tra "phân biệt vector/raster" ở mức EASY sẽ cùng family nhưng khác `variant_no`.

## Migration

```bash
docker compose exec backend alembic upgrade head
```

Migration mới:

```txt
0007_v25_9_14_1_question_family_id.py
```

## Test nhanh

```sql
SELECT question_family_id, difficulty, COUNT(*)
FROM ai_questions
WHERE course_id='course-v1:FPT+MUL211+SU26'
GROUP BY question_family_id, difficulty
ORDER BY COUNT(*) DESC;
```

Kỳ vọng: các câu cùng concept/difficulty nằm cùng family; các family có nhiều variant là nguồn để bản `v25.9.14.2` chọn mỗi family tối đa 1 câu.
