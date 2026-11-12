# CMS-AI — snapshot nguồn

Đọc trực tiếp Git ngày **15/10/2026 (UTC)**, nhánh `feat/import-quiz-cms-old-su26`,
commit [`f961e76a6bb269e09d93c52ea52b96e7f5b028a5`](https://github.com/thaipro23/CMS-AI/commit/f961e76a6bb269e09d93c52ea52b96e7f5b028a5).
Tài liệu này là mốc bàn giao, không tự cập nhật theo catalog và không xác nhận deploy.

## Một AP key, daily lỗi theo scope, video review — 12/11/2026 (Asia/Ho_Chi_Minh)

Baseline `9164170e3507782a033f8fc28d4c163490673635`. [Runbook và quyết định](fixes/AP_DAILY_VIDEO_REVIEW_2026-11-12.md), [AP contract mới](AP_LEARNING_RESULTS_API.md).

- AP dùng một `X-AP-API-Key`, không cần client ID. Secret
  `AP_ANALYTICS_CONFIG_JSON` chứa digest và scope branch/campus rõ ràng. Legacy
  clients JSON chỉ được chấp nhận khi đúng một client. Config mới sai không fallback.
- Daily coordinator không còn biến một lỗi map môn thành dừng mọi scope. Giữ
  class map thành công qua retry, cô lập dependency failure, làm tiếp target lành;
  báo cáo campus/HO thiếu đầu vào không được ghi thành đầy đủ. Validate partition
  mapping và snapshot metadata (kể cả completed+{}); giữ failure_details, nguyên
  nhân/môn/lớp, artifacts, truthful partial outcome của root và scope parent.
- Video: nguyên nhân score35 vẫn NORMAL là trọng số video max45 và escape hatch
  bị trung bình toàn course làm loãng. Nay >=3 video có phép đo đủ căn cứ, hoàn
  thành>=90% nhưng xem<25%, trải >=2 Bài/session nhận TEACHER_REVIEW. Không tự
  kết luận gian lận. Thiếu timing/history hoặc nhảy vị trí không quan sát được
  khi pause/resume là dữ liệu thiếu; dùng marker resume_continuity_checked, giữ
  outer video_playback_v1 để tương thích ML. Marker cũ không tự nâng cấp bởi tail.
- Snapshot behavior audit_v3: bản cũ/không rõ version stale và cần tính lại; GET
  không mutate/reclassify. AP stale summary thống nhất với rows, chỉ đọc version
  scalar trong JSON, không hydrate/trả raw evidence/answers. UI hai trang dùng
  chung tên dấu hiệu tiếng Việt, giữ lý do trung tính, điểm /100 và giây dưới phút.
- Kiểm chứng: full backend **312 failed/1.464 passed/16 skipped**, exact312 node
  lỗi trùng baseline, không lỗi mới. 32 AP tests, 21 daily isolation tests nằm
  trong các scoped suites; frontend **46 tests pass**, lint/typecheck/production
  build đạt. CI source563pass + release6pass/1deselected; integration local
  2fail/14skip do thiếu PostgreSQL/REDIS_URL như baseline. Ruff/compileall/diff
  check đạt. Independent review có các ca
  snapshot completed thiếu đầu ra, paused-gap video và parent partial-success
  sai; đã bổ sung regression RED→GREEN. [Bằng chứng](verification/AP_DAILY_VIDEO_2026-11-12.md).
- CHƯA DEPLOY/CHƯA THAY SECRET/CHƯA TÍNH LẠI PRODUCTION. Cần build backend,
  worker và frontend, cấp key AP, tính lại analytics theo job và nghiệm thu thực tế.
  Job failed a687bbda-c9e6-4620-b3c7-d70d3d8c50b7 không có business-resume API;
  giữ terminal/idempotency, bản sửa áp dụng root active/mới và lịch mới sau deploy.
  PSY1013 vẫn cần đúng một course hoặc map thủ công; không chọn bừa. Không có
  migration/Redis flush/reset Quiz/PVC hoặc sửa status DB trong phiên này.

## AP đọc kết quả phân tích học tập — 09/11/2026 (UTC)

Baseline source `c3b69c3c021f62e8cbd58b5493c1b89582899d25`. Thêm hai GET
`/api/integrations/ap/v1/classes/{ap_class_id}/learning-results` và
`/api/integrations/ap/v1/classes/{ap_class_id}/students/{student_code}/learning-results`.
Contract, cấp key và rollout: [AP API](AP_LEARNING_RESULTS_API.md).

- Xác thực backend riêng bằng client ID/key, SHA-256 digest cấu hình qua Secret
  `AP_ANALYTICS_CLIENTS_JSON`; chỉ scope branch/campus được cấp, fail closed.
  Không dùng session/admin role hoặc credential Dash gọi AP làm credential inbound.
- Resolve đúng AP class/term/block và môn/cơ sở; giữ case student_code, current
  roster và effective course mapping. Alias username trùng ở roster/snapshot
  trả conflict; không lấy tùy ý kết quả người khác.
- Chỉ đọc snapshot hiện có, DB pagination tối đa 200; whitelist response không
  raw answers/evidence/peer identity/internal doctor. Missing khác zero/NORMAL;
  stale giữ nhận định lịch sử kèm trạng thái. Không scan tracking, gọi CMS/AP,
  enqueue, reset Quiz, cập nhật điểm, thay Redis hoặc migration.
- 25 test AP + 30 regression analytics/access pass (55/55); Ruff E9/F63/F7/F82,
  compileall và diff check đạt. Full backend 312 failed/1.418 passed/16 skipped;
  cả 312 node lỗi khớp baseline, không có lỗi mới. [Bằng chứng và danh sách lỗi](verification/AP_LEARNING_RESULTS_2026-11-09.md).
  Independent review phát hiện và đã có regression RED→GREEN cho collision
  roster, blank client ID, cache headers và OpenAPI auth contract.
- CHƯA DEPLOY/CHƯA CẤP SECRET AP/CHƯA NGHIỆM THU PRODUCTION. Cần build backend,
  cấu hình scope/key, đối soát AP IDs và đo query plan/latency PostgreSQL thật.
  SQLite không chứng minh production performance hoặc consistency khi dữ liệu
  đang thay đổi đồng thời; phân trang offset có thể dịch khi roster đổi.

## WEB3023 repair: bỏ Final test khỏi phạm vi — 05/11/2026 (Asia/Ho_Chi_Minh)

Baseline `6d1fed3b2a9cc886b531a55f824a29134ecf1d10`. Output runtime do người
vận hành cung cấp xác nhận Celery 5.4.0 / Kombu 5.4.2 / redis-py 5.2.1 và
offering WEB3023_SU26 có 9 chapter: Bài 1–8 đã published, Final test số 9
không có Release. Đây chưa phải bằng chứng tất cả deployment đã rollout.

- CLI cũ giả định toàn offering chỉ có 8 chapter nên dừng trước tạo job/ghi
  Library. Đã sửa chọn Bài 1–8 trước khi validate/plan; giữ kiểm tra đủ và duy
  nhất từng bài, subject/offering, Release, Library/component IDs và active job.
  Không chọn hoặc sửa Final test, không bỏ guard bằng monkeypatch.
- Có thể chạy bản CLI đã commit qua stdin trong worker hiện tại, không build
  image chỉ để cập nhật script vận hành. Dùng cùng task/service được cài trong
  image đã có, không thay code app trong pod, không sửa dependency/PVC/PYTHONPATH.
- Regression tái hiện trước sửa: 1 failed/12 passed; sau sửa 22 test scope/
  rollback/dependency pass. Full suite: 312 failed/1.393 passed/16 skipped, cùng
  312 tên lỗi so baseline 1.391 passed. Ruff/diff/py_compile đạt; không có Docker/
  K8s execution local để xác nhận 8 job thật.
- CHƯA CHẠY 8 RELEASE/CHƯA VERIFY HIỂN THỊ PRODUCTION. Course copy vẫn cần
  sync Library sau khi job publish hoàn tất. [Cách chạy](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md#phạm-vi-8-bài-khi-offering-có-thêm-final-test).

## Worker Redis transport — 05/11/2026 (Asia/Ho_Chi_Minh)

Baseline `6bede597dc917d9b3d35dd3a5c35500281fcb1d6`, nhánh nghiệp vụ
`feat/import-quiz-cms-old-su26`. Người dùng chọn sửa source và build lại image;
không dùng overlay/PVC/PYTHONPATH hoặc cài nóng pod.

- Cả 4 worker production crash với redis-py VersionMismatch, client 5.2.1.
  Khóa thêm Kombu 5.4.2, giữ Celery 5.4.0/redis-py 5.2.1. Redis server dùng
  chung CMS, queue, credentials và DB index không đổi.
- Thêm regression version gate thật vào CI và `pip check`/Redis transport gate
  vào Dockerfile.prod mà Jenkins thực sự build, để chặn image dependency lỗi.
- Test ban đầu 1 failed giống production; sau sửa 20 test liên quan pass.
  Fresh venv cài đầy đủ bộ Celery/Kombu/redis, pip check và client gate pass;
  không kết nối Redis server trong phép thử này. Full suite: 312 failed/1.391
  passed/16 skipped, cùng 312 tên lỗi baseline. CI subset: 490 passed; release
  contract: 6 passed/1 deselected. Integration local vẫn 2 failed/14 skipped vì
  thiếu PostgreSQL/REDIS_URL. Ruff/diff và 12 repo-index tests đạt. Review độc
  lập không có blocker; không coi full suite hoặc integration là xanh.
- CHƯA BUILD DOCKER/CHƯA DEPLOY/CHƯA VERIFY PRODUCTION. Workspace không có Docker
  hoặc K8s access. 8 Release WEB3023 chưa chạy do worker đang crash; không báo
  lỗi 503 hay cập nhật Library đã được xác minh khỏi trên production.
- [Nguyên nhân, phạm vi và triển khai](fixes/CELERY_REDIS_CLIENT_MISMATCH_2026-11-05.md).

## Hiển thị mã HTML trong câu hỏi — 05/11/2026 (Asia/Ho_Chi_Minh)

Điều chỉnh theo yêu cầu không build image, baseline `2364183c80d8f1dc281bd88d311c427e723c04eb`:
- `backend/republish_web3023_no_build.py` chạy qua Python stdin trên pod đang có.
  Chỉ cần tải script lên máy vận hành rồi `kubectl exec -i ... python -u -`;
  không cần file/script mới có sẵn trong image, không sửa file app trong pod.
- Script dùng modules đã cài sẵn; sửa OLX trong bộ nhớ trước khi gọi connector,
  tái dùng Library đã xác minh, chặn đổi/reset key và xóa component trong process
  riêng. Giữ kiểm tra 8 Bài, snapshot/ID canonical, khóa và durable job/audit.
- Đây là cách vận hành ưu tiên cho yêu cầu hiện tại. CLI nằm trong image ở mục
  sau là phương án khác, không còn là điều kiện bắt buộc để sửa ngay.
- Kiểm chứng: 8 test mới đạt, 72 test liên quan đạt; full suite 312 failed/
  1.390 passed/16 skipped, cùng 312 tên lỗi baseline 1.382 passed. Lint script/
  test mới, py_compile, diff và 12 repo-index tests đạt. Không có runtime DB/CMS.
- Chưa có quyền/kết nối cluster, chưa chạy production; kiểm chứng local và
  giới hạn được ghi trong [runbook](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md#không-build-image-chạy-script-qua-stdin-trong-pod-hiện-tại).

Bổ sung vận hành sau baseline `67003ab83cc8323fbd50b579ff5f824b80442d59`:
- Người dùng yêu cầu chạy lại 8 Bài của WEB3023_SU26, offering
  `f5604c81-3f72-4fa5-8fc0-5dcefd5a26e0`, sau request publish trả 503. Chưa có
  response body/log để kết luận nguyên nhân 503; không coi direct run là đã sửa enqueue.
- Phát hiện rollback force reimport có thể xóa component có sẵn khi verify lỗi.
  Đã chặn xóa khi force, chỉ cleanup first-publish nếu connector xác nhận created.
- Thêm operator CLI `backend/republish_web3023_releases.py`: dry-run mặc định,
  đúng 8 Bài, khóa/chống job trùng, giữ Library/component identity và chạy tuần
  tự tác vụ thật không qua enqueue. Worker nhận captured repair expectations;
  kiểm tra lại mapping trước update và không tự nâng term/đổi key khi repair.
- 64 test liên quan đạt; test rollback trước sửa có 6 failed/2 passed. CLI help
  đạt. Fresh full baseline: 312 failed/1.363 passed/16 skipped; sau sửa: 312
  failed/1.382 passed/16 skipped, cùng 312 tên lỗi. CI subset: 481 passed;
  release contract: 6 passed/1 deselected. Integration smoke vẫn 2 failed/14
  skipped vì thiếu PostgreSQL/REDIS_URL local. Lint các file mới, workflow và
  worker đạt; adapter question_bank_service.py giữ nguyên 18 F401 có sẵn.
  git diff --check và 12 repo-index tests đạt. Review độc lập không còn blocker.
- Code/test local; CHƯA DEPLOY/CHƯA CHẠY 8 BÀI/CHƯA VERIFY PRODUCTION. Workspace
  không có kubectl hoặc kết nối K8s. Không có migration, reset Quiz/điểm hay sửa
  trạng thái job thủ công. [Lệnh và giới hạn](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md#chạy-lại-8-bài-web3023-bằng-k8s-không-qua-bước-enqueue).

Baseline nguồn mới nhất trong phạm vi này: `064efb7c9f756e4dd900c6d0f2456f1cc41cbfd2`;
nhánh sửa `fix/html-question-literal-display-20261105`, tích hợp vào
`feat/import-quiz-cms-old-su26`. Các phần cũ bên dưới giữ mốc/bằng chứng riêng.

- Câu WEB3023 có đáp án `<details>` bị CAPA biến thành HTML thật sau XML parse.
  Exporter bọc và escape text hiển thị; tách rõ grading/attribute/media. Dữ liệu
  Excel/DB và đáp án đúng giữ nguyên. [Hợp đồng và tái xuất](fixes/OPENEDX_LITERAL_HTML_DISPLAY_2026-11-05.md).
- Local: 45 test import/export pass; toàn bộ 254 câu hợp lệ của workbook xuất
  được, 884 lựa chọn giữ đúng text, 36 câu có ký tự HTML. File còn 38 câu chưa
  phù hợp validation import; không tự sửa ý nghĩa/đáp án của các câu đó.
- Full suite: 1.363 passed/16 skipped/312 lỗi nền, không có tên lỗi mới. CI unit
  subset 462 passed và release-contract subset 6 passed; integration smoke
  PostgreSQL/Redis bị chặn do thiếu dịch vụ/env local (2 failed/14 skipped).
  Không báo CI tích hợp xanh. Ruff/diff checks và 12 test repo_index đạt.
- Hiệu năng production: CHƯA ĐO; không thêm truy vấn DB/network vào exporter.
  Browser/Open edX runtime acceptance: CHƯA XÁC MINH; Chromium local thiếu binary.
- Deploy backend/worker, rồi force reimport đúng Release. Bản copy trong course
  cần sync Library riêng. Chưa triển khai hoặc chạy job production; không reset
  Quiz/điểm để chữa hiển thị. Không có migration hay thay đổi CMS-FPT/frontend.

## Tiến độ và nhãn điều kiện thi — 21/10/2026 (Asia/Ho_Chi_Minh)

Baseline đã đối chiếu GitHub: `73ee71c925ac18daf29bc782c5f06ecc31c75c04`.
Nhánh riêng `fix/student-exam-eligibility-labels-20261021`, tích hợp vào
`feat/import-quiz-cms-old-su26` sau khi CI đạt. Thay đổi có source trong changeset
này; chưa có xác minh deploy/production.

- Cột Tiến độ học: **Xem video và Quiz: …%**, **Điểm tổng: …/10** cùng cỡ chữ,
  tách dòng/in đậm 700; dòng thứ ba dùng **Đủ điều kiện thi / Chưa đủ điều kiện thi**.
- Cùng helper với cột Điều kiện thi, cần có Quiz, tất cả Quiz đạt 100% và quyết định
  policy chính thức cho phép. Không suy từ tiến độ 100%, điểm tổng đã làm tròn hoặc
  trạng thái “chưa bị cấm thi” trước ngày cuối. Thiếu dữ liệu luôn có lý do, không
  nhận đủ điều kiện. [Contract chi tiết](ASSESSMENT_GRADE_AND_PROGRESS_CHECK.md).
- Giữ công thức điểm, backend/API/schema, quy tắc ngày cuối, bộ lọc learning_status,
  gợi ý đồng bộ CMS và việc ẩn điểm Assignment. Excel/email, ML, Udemy, CMS-FPT không đổi.
- Kiểm chứng local vừa chạy: `node --test tests/*.test.cjs` tại frontend: **33 passed**;
  `npm run lint`, `npm run typecheck`, `npm run build`: **đạt**;
  `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/tmp/chromium npm run test:ci -- --workers=2`
  tại e2e: **37 passed**, gồm máy tính/điện thoại, font thực tế và hai dòng không chồng.
  Backend pytest cho `test_training_policy_service.py`, `test_assessment_average_grade.py`,
  `test_assignment_ui_suppression.py`: **33 passed**. Test mới đã xác nhận thất bại với
  giao diện cũ trước khi sửa; CSS 600 được phát hiện và sửa thành 700, marker ẩn Assignment
  được giữ nguyên sau hồi quy. Review độc lập không còn lỗi chặn.
- Hiệu năng: **KHÔNG ÁP DỤNG** benchmark mới; chỉ hiển thị từ payload sẵn có, không thêm
  request/query/job. Không tuyên bố hiệu năng production. CI/checks trên PR được xác minh
  riêng trước merge; trạng thái này không phải bằng chứng rollout.
- Việc tiếp theo sau merge: triển khai frontend bằng luồng hiện hành và kiểm tra đúng lớp
  trên dashboard với payload thật. Không có truy cập runtime production trong phiên này.

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
