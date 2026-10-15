# CMS-AI — snapshot nguồn

Đọc trực tiếp Git ngày **15/10/2026 (UTC)**, nhánh `feat/import-quiz-cms-old-su26`,
commit [`f961e76a6bb269e09d93c52ea52b96e7f5b028a5`](https://github.com/thaipro23/CMS-AI/commit/f961e76a6bb269e09d93c52ea52b96e7f5b028a5).
Tài liệu này là mốc bàn giao, không tự cập nhật theo catalog và không xác nhận deploy.

## Thay đổi nguồn gần nhất

| Commit | Đã có trong Git | Kiểm thử ghi trong tài liệu nguồn |
|---|---|---|
| `f961e76` — 15/10 | Quiz ContextVar dùng `None`, mỗi lần đọc normalize trả nested config mới | [10 focused tests](fixes/QUIZ_CONTEXT_DEFAULT_2026-10-15.md) |
| `58ebe0b` — 15/10 | AI quota tách khỏi manual/import, giữ lineage/provenance | [15 workflow cases, 25 frontend tests; typecheck/lint/build](fixes/GENERATION_IMPORT_QUOTA_2026-10-15.md) |
| `762a1ff` — 15/10 | Teacher đa hệ: assignment/class quyết định report scope; metadata merge dưới row lock, report cache v3 | [72 targeted + 53 daily/AP tests](fixes/TEACHER_MULTIBRANCH_REPORT_2026-10-15.md) |
| `6339043` — 14/10 | Daily continuations được publish sau coordinator unlock | [delivery evidence](fixes/DAILY_COORDINATOR_DELIVERY_2026-10-14.md) |
| `2976d52` — 13/10 | Giảm parse grade lặp và sửa analytics max timeout | [performance record](fixes/DASH_GRADE_READ_PERFORMANCE_2026-10-13.md) |

Các số kiểm thử ở trên là **bằng chứng được commit trong nguồn**, không phải suite
ứng dụng vừa được chạy lại khi gọn hóa docs. Tài liệu tại HEAD ghi full backend
`1193 passed, 15 skipped, 311 failed`, tên lỗi khớp baseline có mô tả; suite chưa xanh.
Không sửa hàng loạt fixture/version assertion để che trạng thái này.

## Runtime contract cần mở đúng nguồn

- [VERSION](../VERSION): `25.9.16.7.2.64.16.5.7.2.18`; version không định danh đủ hotfix.
- Alembic nguồn đã tới [0073](../backend/alembic/versions/0073_assessment_average_grade.py);
  xác minh graph/database trước migrate, không dùng head 0065 trong tài liệu tháng 9.
- Daily schedule trong [daily_academic_pipeline.py](../backend/app/services/academic/daily_academic_pipeline.py)
  là `01:00`; timezone và ENV thực tế phải kiểm tra tại runtime.
- Celery entrypoint: `app.worker.celery_app`. Xem [worker](../backend/app/worker.py),
  [config](../backend/app/core/config.py), manifest [deploy](../deploy/) trước điều chỉnh queue/concurrency.
- Plugin của repo AI và plugin tại CMS-FPT là hai bản nguồn cần đối chiếu; không giả định đồng nhất.

## Deploy và việc tiếp theo

**Chưa xác minh production tại snapshot này.** Các fix 15/10 tự ghi chưa deploy.
Teacher/default fix cần backend + workers; quota fix cần thêm frontend. Không cần
CMS-FPT rebuild cho ba fix này. Xác minh image digest/SHA từng thành phần rồi mới
kết luận đã phát hành; tránh trộn worker/backend cũ với code mới.

1. Đối chiếu deployed image với Git và cập nhật bằng chứng acceptance cho teacher đa hệ/quota/context.
2. Teacher `campus_snapshots_exhausted` là business failure: kiểm tra root/attempt;
   transport resume không xử lý terminal root này. Không xóa audit hay đánh dấu snapshot xong giả.
3. Chạy đúng regression theo tác vụ; xem full-suite baseline trong
   [QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt](fixes/QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt).
4. Cần context khác: [INDEX](INDEX.md); cần file: [CODE_INDEX](../CODE_INDEX.md).
