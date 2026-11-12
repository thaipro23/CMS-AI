# CMS-AI — tài liệu theo tác vụ

Entry mặc định: [CURRENT_STATE](CURRENT_STATE.md) khi cần bàn giao;
[CODE_INDEX](../CODE_INDEX.md) khi cần sửa code; [REPO_INDEX](REPO_INDEX.md) để tra file.
Mốc nguồn: `f961e76a6bb269e09d93c52ea52b96e7f5b028a5`, 15/10/2026.

| Cần làm | Chỉ đọc trước |
|---|---|
| Daily lỗi một môn dừng toàn bộ, video tua nhanh bị NORMAL, một key AP | [12/11 isolation + video review](fixes/AP_DAILY_VIDEO_REVIEW_2026-11-12.md) |
| AP hiển thị kết quả phân tích học tập, API key/scope/identity | [AP learning results API](AP_LEARNING_RESULTS_API.md) |
| Vai trò Senior/Tech Lead, chất lượng code, hiệu năng, cập nhật context mỗi phiên bản | [ENGINEERING_STANDARDS](ENGINEERING_STANDARDS.md) |
| Trang /jobs lỗi 500 từ PostgreSQL statement timeout | [hotfix read path 16/10](fixes/JOBS_500_DATABASE_HOTPATH_2026-10-16.md) |
| Daily pipeline treo/continuation sau unlock | [delivery fix 14/10](fixes/DAILY_COORDINATOR_DELIVERY_2026-10-14.md), [recovery](ACADEMIC_DAILY_CONTINUATION_RECOVERY.md) |
| Giảng viên dạy cả Poly/PTCĐ, snapshot exhausted | [teacher scope 15/10](fixes/TEACHER_MULTIBRANCH_REPORT_2026-10-15.md) |
| Quota nhập 30 vẫn phải sinh được 100 câu AI | [generation quota 15/10](fixes/GENERATION_IMPORT_QUOTA_2026-10-15.md) |
| Context Quiz bị chia sẻ mutable default | [context isolation 15/10](fixes/QUIZ_CONTEXT_DEFAULT_2026-10-15.md) |
| Nhãn Đủ/Chưa đủ điều kiện thi, Xem video và Quiz | [assessment contract – hiển thị điều kiện thi](ASSESSMENT_GRADE_AND_PROGRESS_CHECK.md#hiển-thị-tiến-độ-và-điều-kiện-thi-trong-danh-sách-lớp-cms--21102026) |
| Điểm/Final/tiến độ/503 | [assessment contract](ASSESSMENT_GRADE_AND_PROGRESS_CHECK.md), [grade performance](fixes/DASH_GRADE_READ_PERFORMANCE_2026-10-13.md), [503](fixes/SCORE_REFRESH_503_2026-10-12.md) |
| Cột Quiz/subsection | [columns fix 13/10](fixes/QUIZ_SUBSECTION_COLUMNS_2026-10-13.md) |
| Import Quiz SU26 | [spec/operations](IMPORT_QUIZ_CMS_OLD_SU26.md), [verification record](VERIFICATION_IMPORT_QUIZ_CMS_OLD_SU26.md) |
| Câu hỏi HTML/CSS bị trống hoặc biến thành widget Details sau publish | [literal OLX và tái xuất nội dung đã publish](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md) |
| Chạy lại Bài 1–8 WEB3023 qua K8s, giữ nguyên Final test | [operator CLI và phạm vi](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md#phạm-vi-8-bài-khi-offering-có-thêm-final-test) |
| Sửa WEB3023 ngay trên pod hiện tại, không build image | [script độc lập qua stdin](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md#không-build-image-chạy-script-qua-stdin-trong-pod-hiện-tại) |
| AI worker CrashLoopBackOff / Redis transport VersionMismatch | [pin dependency, build gate và triển khai](fixes/CELERY_REDIS_CLIENT_MISMATCH_2026-11-05.md) |
| Nhắc tiến độ qua email | [Mail Send](ACADEMIC_PROGRESS_EMAIL_MAILSEND.md) |
| Video ranking median/MAD / pool ≥30 / tốc độ phát / tắt quiz / replay | [runbook video v2](LEARNING_ANALYTICS_ML_ROLLOUT.md), [thiết kế](superpowers/specs/2026-10-19-video-relative-ranking-design.md), [audit fix](LEARNING_ANALYTICS_AUDIT_FIX_20261009.md) |
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
