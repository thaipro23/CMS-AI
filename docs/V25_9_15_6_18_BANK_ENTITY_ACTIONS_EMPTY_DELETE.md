# v25.9.15.6.18 - Bank Entity Actions + Empty Delete Guard

## Mục tiêu

Thêm nút hành động `...` cạnh các cấp quản lý ngân hàng đề để sửa thông tin cơ bản hoặc xóa nhầm, nhưng chỉ cho xóa khi bên trong hoàn toàn trống.

Áp dụng cho:

- Bộ môn
- Môn
- Phiên bản môn
- Bài/Chapter

## Backend

Thêm API:

```http
PATCH  /api/question-bank-v2/departments/{department_id}
DELETE /api/question-bank-v2/departments/{department_id}
PATCH  /api/question-bank-v2/subjects/{subject_id}
DELETE /api/question-bank-v2/subjects/{subject_id}
PATCH  /api/question-bank-v2/subject-versions/{subject_offering_id}
DELETE /api/question-bank-v2/subject-versions/{subject_offering_id}
PATCH  /api/question-bank-v2/chapters/{chapter_id}
DELETE /api/question-bank-v2/chapters/{chapter_id}
```

Quy tắc xóa:

- Bộ môn: chỉ xóa khi chưa có môn/version bên trong.
- Môn: chỉ xóa khi chưa có version, bài, bank, tài liệu, câu hỏi, release, mapping, quiz.
- Phiên bản môn: chỉ xóa khi chưa có bài, bank, tài liệu, câu hỏi, release, mapping, quiz.
- Bài/Chapter: chỉ xóa khi chưa có bank, tài liệu, câu hỏi, release, mapping, quiz.

Nếu không trống, backend trả thông báo tiếng Việt nêu rõ còn gì bên trong.

## Frontend

Trên các card ở các trang:

- `/bank/departments`
- `/bank/departments/{id}/subjects`
- `/bank/subjects/{id}/versions`
- `/bank/subject-versions/{id}/chapters`

thêm nút `...` với 2 hành động:

- Sửa thông tin
- Xóa

Quyền: chỉ hiện khi user có `manage_settings`.

## Migration

Không cần migration.
