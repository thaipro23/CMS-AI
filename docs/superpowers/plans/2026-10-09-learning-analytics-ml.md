# Learning Analytics ML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm Isolation Forest chạy theo batch để hiển thị bằng chứng bất thường video/quiz riêng, kiểm chứng rồi merge CMS-AI vào `feat/import-quiz-cms-old-su26`.

**Architecture:** Tận dụng worker và aggregate hiện có. Feature builder độc lập cho video/quiz, scorer thuần chạy một lần/nhóm, workflow ghi kết quả vào JSON bằng chứng hiện tại. Bản đầu chạy off/shadow, không thay điểm hoặc phân loại của luật.

**Tech Stack:** Python 3.12, SQLAlchemy/PostgreSQL, Celery, scikit-learn IsolationForest, Next.js/TypeScript. Task dependency sẽ pin phiên bản scikit-learn/NumPy tương thích và xác nhận cài đặt trong image thật trước khi viết scorer.

**Spec:** `docs/superpowers/specs/2026-10-09-learning-analytics-ml-design.md` — đã được người dùng duyệt; trạng thái code/test xem runbook ML.

## Global Constraints

- CMS-AI base cho công việc: PR #13 head `1857c6fc9e588f48f504de81f3c23302f5c892a0`; refresh nhánh đích trước merge. Không merge CMS-FPT chỉ vì CMS-AI được phép merge.
- Mode chỉ `off|shadow`; mặc định off. Shadow chỉ chạy các class ID pilot cấu hình rõ ràng.
- Tối thiểu 50 distinct canonical students, tối đa 5.000 reference rows mỗi nhóm; số mẫu không phải số event/lượt reset.
- Video tối thiểu 3 video đo được; quiz tối thiểu 6 independent non-burst timestamps và metadata server/version hợp lệ.
- Isolation Forest: 100 cây, tối đa 256 mẫu/cây, contamination auto, seed 42, một CPU thread; không ép tỷ lệ outlier.
- Không fit ở GET API; không fit mỗi username; không thay official grade, rule classification, confidence_score hoặc suspicious_score.
- Dữ liệu thiếu không thành zero, không bịa content_version, không suy luận dữ liệu 7/30 ngày từ aggregate tích lũy.
- Latest ML JSON được lưu trong evidence hiện có; không có migration/model registry/kho lịch sử ở bản đầu.
- Mọi số liệu accuracy thực tế phải có nhãn xác nhận và đánh giá tránh leakage. Synthetic pass không được gọi là độ chính xác gian lận.

## Review Focus

- Cùng sinh viên được enroll nhiều lớp: không tăng reference count; teacher không thấy tên người ngoài scope (Task 1/4).
- Recalculate một username: cùng nhóm tham chiếu như full-class và không ghi lại sinh viên khác (Task 3).
- Raw log hết retention nhưng aggregate còn: kết quả không biến thành normal hoặc mất bằng chứng (Task 3).
- Đề random/timeout/submit burst: không nhầm tốc độ hoặc so sánh đề khác nhau (Task 1/5).
- Tắt tính năng/lỗi model/chạy hai job chồng nhau: pipeline và grade vẫn đúng, kết quả stale không hiện như active (Task 3/4).

## File map

Create `backend/app/services/learning_analytics/ml_features.py`: feature schemas, eligibility và cohort keys.

Create `backend/app/services/learning_analytics/ml_anomaly.py`: deterministic batch scoring thuần.

Create `backend/app/services/learning_analytics/ml_workflow.py`: queries theo batch, scope, orchestration và persistence.

Modify `backend/app/core/config.py`, `backend/requirements-runtime.txt`, `backend/requirements-ci.txt` nếu CI không include runtime: cấu hình và dependencies dùng cùng phiên bản.

Modify `backend/app/services/learning_analytics/analytics_core_service.py` và `quiz_integrity_service.py`: gọi workflow tại điểm đã materialize dữ liệu, bảo đảm đường recalc một username.

Modify `backend/app/services/learning_analytics/results.py`, `quiz_detail.py`, `frontend/types/index.ts`, `frontend/app/analytics/learning/page.tsx`: optional ML result và UI bằng chứng.

Create tests `backend/app/tests/test_learning_ml_features.py`, `test_learning_ml_anomaly.py`, `test_learning_ml_workflow.py`, `test_learning_ml_access.py`; add selections trong `scripts/ci-backend-tests.sh`.

Create `scripts/evaluate-learning-ml.py` và `docs/LEARNING_ANALYTICS_ML_ROLLOUT.md`: offline report và vận hành pilot.

### Task 1: Đặc trưng có provenance và nhóm tham chiếu

**Interfaces:** `MLFeatureRow(subject_key: str, family: str, cohort_key: str, features: dict[str, float], cutoff: datetime)`; `MLFeatureBuild(row: MLFeatureRow | None, reasons: tuple[str, ...])`. `build_video_features(*, subject_key, course_id, outline_fingerprint, videos, cutoff) -> MLFeatureBuild`; `build_quiz_features(*, subject_key, course_id, unit_usage_key, attempt, items, cutoff) -> MLFeatureBuild`. Workflow dedup bằng canonical student và nhóm, không dùng AP class ID làm student key.

- [ ] Viết `test_missing_duration_not_zero`, `test_three_measurable_videos_required`, `test_untrusted_start_and_missing_version_rejected`, `test_timeout_burst_excluded`, `test_response_set_changes_cohort`, `test_cross_class_student_dedup`. Assert row None và reason đúng khi thiếu nguồn; khác version có cohort key khác; 20 events cùng người vẫn chỉ một reference row.
- [ ] Chạy `cd backend && pytest -q app/tests/test_learning_ml_features.py`; xác nhận fail do thiếu implementation.
- [ ] Implement builders theo spec; reject NaN/Inf/negative elapsed, UTC-normalize cutoff, bỏ dữ liệu sau cutoff. Video features có tên `completion_watch_gap`, `watch_ratio`, `seeks_per_watch_minute`, `passive_ratio`; quiz có `seconds_per_independent_submission`, `successful_resets_per_attempt`, `submissions_per_response`.
- [ ] Chạy lại tests và regression telemetry/version hiện có; xác nhận metadata thiếu không bị nâng chất lượng.
- [ ] Commit `feat(analytics): build provenance-aware ML features`.

### Task 2: Isolation Forest theo batch, kết quả có thể tái hiện

**Interfaces:** `score_cohorts(rows: list[MLFeatureRow], *, min_students: int = 50, max_students: int = 5000) -> dict[str, dict]`. Key gồm family/cohort/subject, tránh đè video bằng quiz. Result dùng status `SCORED|INSUFFICIENT_DATA|ERROR`, reason_codes, algorithm/model_version/feature_version, cohort_digest, reference_count, cutoff, features, anomaly_score, reference_percentile, outlier, deviations. Không dùng `probability`.

- [ ] Kiểm tra runtime/CI dependency include chain; pin cùng phiên bản scikit-learn và dependencies cần thiết trong requirements đang dùng, kiểm tra wheel Python 3.12 và image production. Ghi phiên bản thực tế vào model_version; không thay đại trà dependencies khác.
- [ ] Viết tests: 49 distinct students trả BASELINE_TOO_SMALL; 50 đủ điều kiện; duplicate subject không tăng mẫu; constant vectors trả CONSTANT_FEATURES; shuffle rows cùng seed cho cùng digest/score; đồng loạt mẫu thường không bị ép đúng 5%/10% outlier; sample hơn 5.000 ổn định; reject NaN.
- [ ] Chạy `cd backend && pytest -q app/tests/test_learning_ml_anomaly.py`; xác nhận fail rồi implement scorer với tham số spec.
- [ ] Chạy tests; synthetic dataset có điểm lệch rõ phải đứng cao hơn median nhóm, không assert precision/gian lận. `deviations` lấy median/IQR và không được mô tả là model attribution.
- [ ] Commit `feat(analytics): score comparable cohorts with Isolation Forest`.

### Task 3: Worker, persistence và fallback

**Interfaces:** `LearningMLWorkflow(db).score_behavior(*, class_id: str, course_id: str, target_usernames: list[str], cutoff: datetime) -> dict`; `score_quiz(*, class_id, course_id, target_usernames, cutoff) -> dict`. Chỉ ghi ML evidence cho target; queries dựng tham chiếu từ roster/course đủ phạm vi bằng batch, không từ arbitrary username người gọi.

- [ ] Viết tests cho off không fit, shadow ngoài pilot không fit, recalc single-user/full-class cùng reference digest, single-user không ghi người khác, một fit/nhóm, aggregate còn sau raw deletion, exception model không làm mất rule result/grade, cutoff race không ghi kết quả cũ lên snapshot mới.
- [ ] Chạy `cd backend && pytest -q app/tests/test_learning_ml_workflow.py`; xác nhận fail.
- [ ] Thêm config như spec, workflow module và integration hooks. Khi rules ghi đè evidence, merge ML theo phiên tính mới có scope/cutoff; atomic update guard dùng calculated_at để không ghi kết quả vào snapshot mới hơn. Thêm metrics counts scored/skipped/error, elapsed_ms, reference count không kèm PII/answers.
- [ ] Xác nhận đường quiz recalc không refresh integrity lần nữa làm mất ML; đường riêng username dùng full permitted reference pool, output chỉ target. Không thêm query fit vào API đọc.
- [ ] Chạy workflow + analytics/official grade regression; test so sánh checksum grade và snapshot official trước/sau. Memory sample cap được kiểm tra trước khi materialize ma trận.
- [ ] Commit `feat(analytics): persist shadow ML evidence in analytics workers`.

### Task 4: API/UI bằng chứng, quyền và stale

**Interfaces:** `MLAnalysis` optional dưới evidence, cùng schema scorer; serialized disabled/stale status không trả outlier như active. Mảng family video/quiz tách riêng; không expose reference usernames/answer payloads.

- [ ] Viết API tests teacher chỉ đọc lớp được phép; không lộ baseline identities; legacy evidence không có ml vẫn trả bình thường; mode off trả disabled; feature version/cutoff mismatch trả stale. UI tests cho scored/skipped/error và baseline thiếu.
- [ ] Chạy `cd backend && pytest -q app/tests/test_learning_ml_access.py`; xác nhận fail trước implementation.
- [ ] Bổ sung serializers và TypeScript optional fields. Thẻ “Phân tích học máy” hiển thị family, trạng thái, số người tham chiếu, thời điểm, chỉ số so với nhóm và độ lệch; copy không có “xác suất gian lận”. Không đổi count/tổng phân loại luật để tránh dashboard hiểu sai.
- [ ] Chạy API tests; `cd frontend && npm run typecheck`, lint phần thay đổi, production build và Playwright drawer/permission smoke bằng harness CI hiện có.
- [ ] Commit `feat(analytics): show scoped ML evidence in student drawer`.

### Task 5: Đánh giá offline và báo cáo thực tế

**Interfaces:** `scripts/evaluate-learning-ml.py --audit PATH --output PATH --seed 42` chạy read-only trên input/disposable DB, không cần production credentials. JSON output có eligibility_counts, skipped_by_reason, scored_groups, score_distribution, rule_ml_disagreement, duplicate_student_checks, official_hash_before_after, latency và runtime versions.

- [ ] Viết tests script cho export thiếu raw context, legacy missing version, inconsistent subject mapping; assert không invent phiên bản/nhãn và official hashes bằng nhau.
- [ ] Chạy tests fail; implement CLI dùng Task 1/2, không tạo nhãn bằng rules và không sửa archive input.
- [ ] Replay audit 83 sinh viên đã phân tích; công bố đúng số đủ điều kiện theo từng family. Nếu mọi nhóm dưới 50 thì báo zero scored, dùng synthetic chỉ kiểm chứng thuật toán/chạy code, chờ dữ liệu mới để đánh giá thực tế.
- [ ] So sánh luật/ML, kiểm tra mẫu ML đánh dấu và mẫu không đánh dấu. Không dùng disagreement làm lỗi nếu chưa có nhãn giáo viên; không gọi đây là accuracy. Thiết kế pilot lấy mẫu ngẫu nhiên cả hai nhóm để giảm selection bias.
- [ ] Đo 1.000 và 5.000 rows với 100 cây; budget ban đầu 10 giây mỗi cohort, incremental RSS dưới 256 MiB trên môi trường ghi rõ CPU/runtime, không coi benchmark scratch là SLA production. Nếu vượt thì tối ưu trước pilot, không bỏ sample cap.
- [ ] Commit script/tests và báo cáo phương pháp `test(analytics): validate shadow ML eligibility and replay`.

### Task 6: CI, merge đúng nhánh và rollout riêng

- [ ] Thêm tests vào `scripts/ci-backend-tests.sh`; chạy unit/current-behavior, PostgreSQL/Redis integration, compile/Ruff, frontend checks, image/Compose và Playwright. So với base cho lỗi full suite cũ; không claim full suite xanh chỉ vì selection xanh.
- [ ] Review toàn diff và kiểm tra nguồn official grades, timer/timeout, RBAC, worker bounds. Cập nhật audit docs với kết quả ML thực tế và dependency versions; không sửa PR body thành “accuracy đã xác nhận”.
- [ ] Fetch nhánh đích mới nhất, update/rebase nhánh sửa không force nhánh đích; rerun checks nếu code/base đổi. Đẩy branch rồi cập nhật/tạo PR bao gồm audit fix và ML, kiểm tra phạm vi không có thay đổi ngoài mục tiêu.
- [ ] Khi CI của đúng head xanh, đổi PR khỏi draft và merge CMS-AI bằng GitHub plugin với expected_head_sha vào `feat/import-quiz-cms-old-su26` theo quyền người dùng đã cấp. Xác nhận merged và target SHA; merge không đồng nghĩa deploy.
- [ ] Ghi rollout runbook: ML default off; sau build/deploy bật shadow cho lớp đủ dữ liệu, theo dõi queue/CPU/RAM, kiểm tra dashboard. Quiz family cần CMS-FPT 0.4.17 runtime; PR #3 chưa merge không được coi là telemetry đã có.
- [ ] Chạy pilot qua ít nhất hai đợt thu thập, thu nhãn giáo viên từ flagged và unflagged. Nếu đủ nhãn, báo precision/recall kèm sample counts và cách split tránh leakage; chưa đủ thì chỉ báo coverage/chất lượng log. Chưa bật automated actions trong phạm vi này.
- [ ] Kiểm tra rollback `ANALYTICS_ML_MODE=off`: pipeline luật/grades hoạt động, cờ ML cũ không được hiển thị như active. Commit `docs(analytics): document ML pilot and rollback` trước merge; kết quả vận hành sau deploy ghi riêng.

## Handoff

Đề xuất thực hiện trực tiếp từng task trong phiên này, kiểm tra độc lập toàn diff trước merge. Đã được người dùng duyệt ngày 09/10. Source và kiểm thử được tiếp tục trên nhánh mới nhất ngày 16/10; trạng thái merge/deploy và giới hạn hiện tại xem `docs/CURRENT_STATE.md` và `docs/LEARNING_ANALYTICS_ML_ROLLOUT.md`.
