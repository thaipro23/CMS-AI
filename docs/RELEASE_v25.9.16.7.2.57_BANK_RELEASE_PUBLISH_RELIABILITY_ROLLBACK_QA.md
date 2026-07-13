# v25.9.16.7.2.64.12 — Bank Release Publish Reliability + Rollback QA

## Mục tiêu

Tăng độ tin cậy quy trình Bank Release trước khi vận hành thật: chốt bộ đề, đưa lên CMS/Open edX Library, tạo Quiz/Final test và rollback. Bản này không gọi Open edX trong request QA, không tạo job và không thay đổi dữ liệu.

## Thay đổi chính

- `GET /api/question-bank-v2/releases/{release_id}/publish-audit`
- UI `/bank/chapters/{chapterId}` hiển thị panel `QA publish/rollback` cho Release mới nhất.
- `scripts/bank-release-publish-audit-report.sh` xuất JSON/Markdown evidence.
- Phân loại audit status: `PUBLISHED_VERIFIED`, `READY_TO_PUBLISH`, `READY_WITH_WARNINGS`, `BLOCKED`.
- Check các rủi ro: thiếu component id, key thư viện lệch, duplicate component id, câu hỏi status chưa đồng bộ, Quiz/Final test instance đang hiệu lực, rollback cần dọn thủ công.

## An toàn dữ liệu

- Read-only.
- Không publish.
- Không rollback.
- Không enqueue job.
- Không gọi Open edX connector.
- Không mutate DB.

## Migration

Không có migration mới. Latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
