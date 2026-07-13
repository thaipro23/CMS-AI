# v25.9.16.7.2.64.13 — Bank Workflow UX Completion

## Cây Bank chuẩn

```text
Bộ môn → Môn học → một Phiên bản môn cuối theo học kỳ → Bài/Chapter → Câu hỏi
```

Release và Quiz là workflow đầu ra, không phải node hierarchy.

## Frontend

- Môn, Phiên bản môn và Bài dùng `EnterpriseDataTable` + URL state + sticky columns + 20/50/100 pagination.
- Chapter Question table dùng server-side filter/sort/pagination.
- Hỗ trợ chọn tất cả trên trang và chọn toàn bộ kết quả đang lọc; hai scope được giải thích rõ.
- Question preview hiển thị options, đáp án đúng, explanation, source evidence và quality/status.
- Release preview đọc snapshot `ai_bank_release_questions`, không lấy câu mới nhất ngoài Release.
- Import Excel theo flow template → validate → preview → confirm → Celery job.
- Có `bank-question-import-errors.xlsx` cho file lỗi và CSV export theo filter/selection.
- Confirm dialog cho bulk reject, chốt Release và publish CMS.

## Backend

- `GET /bank-versions/{id}/questions/page`
- `GET /bank-versions/{id}/questions/export.csv`
- `GET /bank-versions/{id}/questions/import-template.xlsx`
- `POST /bank-versions/{id}/questions/import-preview`
- `GET /bank-versions/{id}/questions/import-errors/{token}.xlsx`
- `POST /bank-versions/{id}/questions/import-job`
- `GET /releases/{release_id}/preview`
- Celery `bank_question_import_task`

Import preview có giới hạn 10 MB, tối đa 2.000 dòng, kiểm tra zip/OpenXML, preview ownership và expiry hai giờ. Câu import luôn `pending_review`; không tự approve, Release hoặc publish.

## Migration

Không có migration mới.
