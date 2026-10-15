# CMS-AI — tài liệu theo tác vụ

Entry mặc định: [CURRENT_STATE](CURRENT_STATE.md) khi cần bàn giao;
[CODE_INDEX](../CODE_INDEX.md) khi cần sửa code; [REPO_INDEX](REPO_INDEX.md) để tra file.
Mốc nguồn: `f961e76a6bb269e09d93c52ea52b96e7f5b028a5`, 15/10/2026.

| Cần làm | Chỉ đọc trước |
|---|---|
| Daily pipeline treo/continuation sau unlock | [delivery fix 14/10](fixes/DAILY_COORDINATOR_DELIVERY_2026-10-14.md), [recovery](ACADEMIC_DAILY_CONTINUATION_RECOVERY.md) |
| Giảng viên dạy cả Poly/PTCĐ, snapshot exhausted | [teacher scope 15/10](fixes/TEACHER_MULTIBRANCH_REPORT_2026-10-15.md) |
| Quota nhập 30 vẫn phải sinh được 100 câu AI | [generation quota 15/10](fixes/GENERATION_IMPORT_QUOTA_2026-10-15.md) |
| Context Quiz bị chia sẻ mutable default | [context isolation 15/10](fixes/QUIZ_CONTEXT_DEFAULT_2026-10-15.md) |
| Điểm/Final/tiến độ/503 | [assessment contract](ASSESSMENT_GRADE_AND_PROGRESS_CHECK.md), [grade performance](fixes/DASH_GRADE_READ_PERFORMANCE_2026-10-13.md), [503](fixes/SCORE_REFRESH_503_2026-10-12.md) |
| Cột Quiz/subsection | [columns fix 13/10](fixes/QUIZ_SUBSECTION_COLUMNS_2026-10-13.md) |
| Import Quiz SU26 | [spec/operations](IMPORT_QUIZ_CMS_OLD_SU26.md), [verification record](VERIFICATION_IMPORT_QUIZ_CMS_OLD_SU26.md) |
| Nhắc tiến độ qua email | [Mail Send](ACADEMIC_PROGRESS_EMAIL_MAILSEND.md) |
| Analytics/tracking/fraud | [implementation reference](QUIZ_TRACKING_IMPLEMENTATION.md) — dài, chọn heading liên quan; tra thêm `find "analytics" --docs` |
| Cache giảng viên | [Redis teacher overview](REDIS_TEACHER_OVERVIEW.md) |
| Hạ tầng/deploy | [RUN_CURRENT](../RUN_CURRENT.md), [MinIO](EXTERNAL_MINIO.md) |
| API/frontend architecture | [API](API.md), [frontend](FRONTEND_STRUCTURE.md); đối chiếu source hiện tại |

## Quy tắc cần giữ

- RBAC ở API/service; menu không cấp quyền. Bank và vận hành đào tạo giữ scope riêng.
- Campus AP sync lấy danh mục thủ công `/premises`, payload dùng `campus_code`.
- RollNumber/`student_code` giữ đúng case; không suy danh tính từ AP username/email.
- Teacher identity dùng chung giữa Poly/PTCĐ; assignment/class xác định scope report,
  profile branch không phải tư cách độc quyền. Snapshot đã build vẫn phải có branch rõ.
- Manual/import không tiêu AI quota; câu AI giữ quy tắc quota theo trạng thái nguồn.
- Giữ lock, idempotency, publish sau commit; terminal business-exhausted daily root
  không tự mở lại chỉ bằng redeploy hay transport-resume.
- Source/test/deploy là ba trạng thái riêng; không xem tài liệu release là log production.

## Lịch sử và thiết kế

`docs/history/`, root `AI_SERVER_PROJECT_*`, `RUN_V*`, `RELEASE_v*`, `VERIFICATION_v*`,
`docs/V*` và `docs/superpowers/` giữ context/ADR/proposal cũ. Chúng có thể mô tả
schedule, migration, quota hoặc trạng thái đã bị thay thế. Tra một file bằng
`python scripts/repo_index.py find "tu_khoa" --docs --history --limit 10`.

Master cũ được giữ tại [history/MASTER_CONTEXT_DASH_CMS_2026-09.md](history/MASTER_CONTEXT_DASH_CMS_2026-09.md).
Không đọc hết lịch sử khi khởi động; dùng Git diff/log của file liên quan để phân xử.
