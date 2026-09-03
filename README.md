# AI Server Open edX — v25.9.16.7.2.64.16.5.7.2.18

Current feature branch: **SU26 Legacy Quiz Import & Fast Subject Search**.

This branch extends the known-good `.16` baseline without replacing Open edX core. Question Bank has a canonical response schema for **Một đáp án**, **Nhiều đáp án**, **Chọn và điền ô trống**, **Trả lời ngắn**, and **Trả lời số**. The Department screen includes fast subject lookup, while `/import-quiz-cms-old` validates legacy multi-sheet Excel workbooks and imports them into the subject's **SU26** version. Every imported question records the importer and starts in **Chờ duyệt**. Legacy questions without concept/difficulty remain eligible after review: Quiz planning treats missing concepts independently and missing difficulties as flexible quota inventory.

## Runtime scope

- Question authoring/review/release: `/bank`
- Fast subject lookup: `/bank/departments`
- Legacy Excel preview/import: `/import-quiz-cms-old` (bổ sung ảnh thiếu hoặc loại câu lỗi trước khi import)
- Quiz/Final test planner: `/bank/quiz`
- Open edX publish continues through the connector/worker flow; no Open edX core patch is required.
- AP synchronization remains scoped to subjects selected CMS/Udemy in `/subject-management` from `.16`.
- Heavy generation/publish/quiz operations remain persistent Celery jobs.
- Database schema head: `0061_v25_9_16_7_2_64_39`.

Release notes: `RELEASE_v25.9.16.7.2.64.16.5.7.2.18_QUESTION_TYPES_ERROR_HARDENING.md`.
Verification: `VERIFICATION_v25.9.16.7.2.64.16.5.7.2.18.md`.
Deploy: `RUN_V25_9_16_7_2_64_16_5_7_2_18.md`.

Feature specification and operations guide: [`docs/IMPORT_QUIZ_CMS_OLD_SU26.md`](docs/IMPORT_QUIZ_CMS_OLD_SU26.md).
Verification report: [`docs/VERIFICATION_IMPORT_QUIZ_CMS_OLD_SU26.md`](docs/VERIFICATION_IMPORT_QUIZ_CMS_OLD_SU26.md).
