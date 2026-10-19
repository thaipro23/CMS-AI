# CMS-AI — snapshot nguồn

Đọc trực tiếp Git ngày **15/10/2026 (UTC)**, nhánh `feat/import-quiz-cms-old-su26`,
commit [`f961e76a6bb269e09d93c52ea52b96e7f5b028a5`](https://github.com/thaipro23/CMS-AI/commit/f961e76a6bb269e09d93c52ea52b96e7f5b028a5).
Tài liệu này là mốc bàn giao, không tự cập nhật theo catalog và không xác nhận deploy.

## Cập nhật quy trình — 16/10/2026 (Asia/Ho_Chi_Minh)

Nguồn đọc trước thay đổi docs này: [`01b00174ecf29506da3acf2e1f412b118bb655a9`](https://github.com/thaipro23/CMS-AI/commit/01b00174ecf29506da3acf2e1f412b118bb655a9).
Giữ nguyên mốc nguồn/nghiệp vụ và bằng chứng kiểm thử ở các phần bên dưới.

- Ghi rõ vai trò Principal Architect / Tech Lead / Senior Engineer trong `AGENTS.md`;
  quy tắc chuẩn ở [ENGINEERING_STANDARDS](ENGINEERING_STANDARDS.md).
- Mỗi phiên bản/hotfix/bàn giao phải cập nhật snapshot, tài liệu bị ảnh hưởng và
  catalog; chất lượng và tuyên bố hiệu năng cần bằng chứng, rủi ro phải được bàn giao.
- Phạm vi lần này: docs/hướng dẫn và catalog metadata; không thay đổi source ứng dụng,
  schema, VERSION/package, cấu hình runtime hoặc deploy. Hiệu năng ứng dụng: **KHÔNG
  ÁP DỤNG** cho thay đổi docs; không có số đo mới hoặc acceptance production mới.
- Kiểm chứng đã thực hiện: đối chiếu catalog nền với Git tree tại mốc nguồn trên;
  kiểm tra target của link Markdown, JSON và whitespace của tài liệu thay đổi.
  Không chạy lại test ứng dụng cho thay đổi thuần docs. Đối chiếu SHA/inventory
  catalog mới và HEAD sau publish là điều kiện bàn giao, kết quả ghi ở bàn giao cuối.
- Việc tiếp theo: áp dụng tiêu chuẩn cho thay đổi kế tiếp; các acceptance/deploy còn
  mở bên dưới vẫn cần xác minh. Bộ quy tắc trong docs không phải CI gate tự động.

## Hotfix /jobs HTTP 500 — 16/10/2026 (Asia/Ho_Chi_Minh)

Baseline Git: `4e2d9e41bbad5460d971d08d527e53cc14108924`.
Nhánh đề xuất: `fix/jobs-500-db-read-hotpaths-20261016`.
Runtime evidence: backend pod 16/10 10:42, QueryCanceled (10s) trên
academic_class_sync_jobs status=failed ORDER BY created_at LIMIT 100 và
COUNT(*) analytics_tracking_events. Planner ước tính 215752 jobs, 14447732
tracking events; `pg_stat_user_tables` cho số gần tương đương.

Thay đổi trong source hotfix: Alembic 0074 tạo composite index
(status, created_at) concurrently; `/health/ready` yêu cầu 0074; batch
RBAC class-job giữ đúng teacher/campus-branch/subject; `ops_status` tránh
exact count toàn tracking, trả số lượng ước tính có nhãn và readiness
vẫn dùng bounded exact threshold; batch GROUP BY rollout, không đổi
effective course mapping. Xem [runbook hotfix](fixes/JOBS_500_DATABASE_HOTPATH_2026-10-16.md).

Kiểm chứng sau sửa 16/10:
- GitHub Actions run `38867797375` trên hotfix HEAD
  `99676ac0aa4d63f6df872aa8a215fe44653174de` đã kết thúc **success**:
  backend quality/integration, frontend lint/typecheck/build,
  Playwright browser smoke, image/Compose và npm lockfile đều passed.
- Migration 0074 đã vượt bước Alembic upgrade trên PostgreSQL CI;
  các regression hotfix đã được đưa vào `scripts/ci-backend-tests.sh`.
  Đây là kết quả CI, không phải kiểm thử trên dữ liệu production.
- PR [#14](https://github.com/thaipro23/CMS-AI/pull/14) đã **merge**
  vào `feat/import-quiz-cms-old-su26` tại commit
  `f021cb1d97dd151063c49a8b70023e1241d933ca`.
- Đã xác minh HEAD sau merge bằng GitHub. Không có thay đổi ở CMS-FPT.

Trạng thái bàn giao: **ĐÃ MERGE CODE VÀ PASS CI**; UAT trên workload
tương đương production: **CHƯA XÁC MINH**; migration/index trên PostgreSQL
production: **CHƯA CHẠY**; deployment Kubernetes: **CHƯA TRIỂN KHAI**;
hai endpoint thực tế sau rollout, p50/p95/p99 và query plan sau sửa:
**CHƯA ĐO**. Chỉ triển khai sau migration/UAT an toàn theo runbook.
CMS-FPT không thay đổi. Không tăng global DB statement timeout.
Rủi ro: pg_class.reltuples là ước tính có độ trễ, concurrent index vẫn
có thể chờ transaction/lock, cần kiểm tra hiệu quả index trên dữ liệu thật.

## Video relative ranking v2 — 19/10/2026 (Asia/Ho_Chi_Minh)

Baseline đã đối chiếu GitHub: `dbd0c62d268fc04de3a4b327eaa03a3d57b1e524`
(ML v1 đã merge PR #13). Nhánh riêng `feat/video-learning-ranking-20261019`.
[Runbook hiện hành](LEARNING_ANALYTICS_ML_ROLLOUT.md) và
[thiết kế v2](superpowers/specs/2026-10-19-video-relative-ranking-design.md)
là nguồn chuẩn cho video; thay thế ngưỡng/thuật toán v1.

- Video trước: median/MAD làm điểm xếp hạng chính, Isolation Forest 200 cây đối chiếu.
  Hiện hai percentile khi khác nhau; khi gần nhau ưu tiên giải thích median/MAD.
  API/UI không có cờ outlier hoặc nhãn kết tội; vẫn giữ điểm và kết quả luật.
- Tối thiểu 30 người khác nhau; 30–49 “Độ tin cậy thấp”. Pool nhiều course có cấu hình
  rõ ràng, chỉ active/effective rosters; gom video theo người, loại trùng, nhóm theo
  exposure/độ dài. Trần 20 course, 20.000 roster, 50.000 source rows, 5.000 references.
- Đo tiến trình nội dung riêng, chuẩn hóa tốc độ phát; legacy/mất mốc phát đầu/thiếu vị
  trí không đủ lịch sử. Giữ event identity tại timestamp trùng, incremental idempotency.
  API chỉ đọc saved evidence; stale/version/pool/RBAC guards và target-only writes.
- Global `ANALYTICS_ML_MODE=off`, pilot IDs rỗng; video flag=true, quiz flag=false.
  Không có migration. Quiz chỉ xét bật sau telemetry PR #3 được port/deploy tương thích
  plugin 0.4.18+ và đủ provenance server; không downgrade về gói 0.4.17.
- Kiểm chứng local sau sửa review: 116 focused backend, 28 frontend unit/rendered,
  35 Playwright smoke; lint/typecheck/build và fatal Ruff/compile đạt. Năm seed
  0,1,7,42,99: fixture synthetic top 5 trùng 100% (yêu cầu ≥80%); thiếu dữ liệu,
  công tắc tắt, cross-course pool và chèn người giả lập đều có regression.
- Full backend trên source sạch: 1.350 passed / 16 skipped / 312 failed; bộ tên lỗi
  nền đối chiếu [baseline](fixes/LEARNING_ML_TEST_BASELINE_2026-10-16.txt), không coi
  full suite là xanh. PostgreSQL/Redis/migration/concurrency và image/Compose
  là cổng CI của đúng PR head, không suy ra từ SQLite hoặc benchmark scorer.
- Replay: 3 lớp / 83 người, 0 nhóm được xếp hạng. Cả 83 thiếu ba video đo hợp lệ;
  38 có video legacy thiếu playback measurement; một measurement sai.
  5.195 nhóm người/quiz chuẩn hóa được giữ tắt. Official export hash trước/sau bằng nhau.
  Chưa có accuracy thực tế hoặc nhãn xác nhận giảng viên.
- Benchmark synthetic process mới: 1.000/5.000 người = 0,9252/1,1019 giây;
  incremental peak RSS 110,84/123,51 MiB. Không gồm DB I/O/concurrent app worker
  và không phải SLO production.
- Review độc lập một lượt; sửa các lỗi cùng timestamp, thiếu phát đầu, tiếp tục
  đọc sau disable và outline replay cũ/mới. Có RED→GREEN và test materialization;
  không có minor hoãn. Chi tiết: [verification](fixes/VIDEO_RELATIVE_RANKING_VERIFICATION_2026-10-19.md).
- Trạng thái merge/CI: xem PR của nhánh `feat/video-learning-ranking-20261019`.
  **CHƯA DEPLOY / CHƯA BẬT PILOT / CHƯA XÁC MINH PRODUCTION** trong phiên này;
  CMS-FPT không đổi. Sau deploy đồng bộ backend/worker/frontend, thu số đo video mới,
  chọn pool/pilot phù hợp và lấy mẫu giảng viên xác minh.

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
