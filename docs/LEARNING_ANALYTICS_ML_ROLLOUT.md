# Learning Analytics ML: vận hành và đánh giá

Nguồn nền: CMS-AI `c42cba8` (16/10/2026), tích hợp audit fix PR #13 và thiết kế
[ML đã duyệt](superpowers/specs/2026-10-09-learning-analytics-ml-design.md).
Đây là phát hiện khác biệt không giám sát bằng Isolation Forest trên batch hiện tại.
Chưa có nhãn xác nhận để đo accuracy/precision/recall; không dùng nhãn luật làm ground truth.

## Contract và giới hạn

- Video và quiz có mô hình/nhóm riêng; không đổi official grades, classification,
  confidence_score hoặc suspicious_score của luật. GET chỉ đọc evidence đã lưu.
- Mỗi nhóm cần ít nhất 50 người khác nhau, lấy mẫu tối đa 5.000 người theo hash ổn định;
  người học nhiều lớp/làm nhiều lượt không được tính thành nhiều người tham chiếu.
- Video cần ba video đo hợp lệ trong outline hiện tại. Chuẩn hóa block ID đầy đủ/rút gọn
  theo định danh block chính xác, không so khớp chuỗi con. Nhóm theo course/outline/exposure.
- Quiz cần start/nonce server, phiên bản/slot/variant hợp lệ, sáu mốc nộp độc lập không burst;
  chọn lượt đủ điều kiện đầu tiên mỗi sinh viên/cohort đề; evidence mới nhất hiển thị cohort của lượt đủ điều kiện gần nhất. Đề random khác tập câu không gộp nhóm.
- Feature tích lũy theo cutoff, không đại diện cửa sổ 7/30 ngày. Không bịa metadata lịch sử.
- Timing có marker `server_submissions_v1`; browser canonical không được nâng thành server timing.
  Khi materialize lại, không union timing cũ thiếu marker. Reset ML có marker
  `server_reset_new_session_v1`: reset thuộc phiên mới được tạo thành công; lưu riêng
  `successful_reset_times` để toàn bộ/retention-truncated raw reconstruction cùng kết quả.
  Counter/reset evidence của luật hiện có giữ cách đếm cũ; không dùng nó làm zero mặc định ML.
- 100 cây, max_samples <=256, seed 42, contamination auto, n_jobs=1 và threadpool limit=1.
  Thư viện runtime: NumPy 2.2.1, scikit-learn 1.6.1, SciPy 1.15.1,
  joblib 1.4.2, threadpoolctl 3.5.0; CI và image dùng cùng requirements-runtime.
- Worker batch sau vòng lặp sinh viên, dùng full permitted reference pool khi tính riêng
  một người. Chỉ persist kết quả của target (kể cả rule rows/alias cleanup khi recalc riêng); khóa/refetch evidence và guard snapshot/cutoff tránh job cũ
  đè kết quả mới. Trần 20.000 roster entries và 50.000 source rows/table; vượt trần trả lỗi
  phân tích bổ sung, không cắt âm thầm thành một nhóm nhỏ hay đổi điểm.
- Lỗi ML nằm trong savepoint riêng. Mã trạng thái/data quality và counts được log, không
  log tên/đáp án tham chiếu. Kết quả stale/sai version/sai scope không hiện cờ đang hoạt động.
- JSON giữ kết quả mới nhất, chưa có model registry/kho lịch sử. Median/IQR chỉ mô tả
  độ lệch, không phải feature attribution hay giải thích nhân quả của mô hình.

## Bật pilot sau deploy

Mặc định trong source và env mẫu:

```dotenv
ANALYTICS_ML_MODE=off
ANALYTICS_ML_PILOT_CLASS_IDS=
ANALYTICS_ML_MIN_REFERENCE_STUDENTS=50
ANALYTICS_ML_MAX_REFERENCE_STUDENTS=5000
```

Sau khi build/deploy backend, worker-analytics và frontend cùng source, chỉ bật shadow
cho class ID đã chọn. Ví dụ cấu hình: `ANALYTICS_ML_MODE=shadow` và
`ANALYTICS_ML_PILOT_CLASS_IDS=<class-id-1>,<class-id-2>`. Backend và worker phải có cùng
cấu hình; áp dụng cấu hình vào process đang chạy theo runbook triển khai hiện có.
Không tự bật toàn hệ thống khi chuỗi class ID rỗng. Dùng thao tác tính lại lớp hiện có;
ML không chạy trong request đọc dashboard và không tạo queue/service mới.

CMS-FPT `fpt-indigo-ui` đọc lại ngày 16/10 đã có unit-reset **0.4.18**, nhưng chưa có
`analytics.py`/hook bổ sung của [PR #3](https://github.com/thaipro23/CMS-FPT/pull/3).
PR #3 cũ là 0.4.17, vẫn draft và chưa merge. Trước pilot quiz cần tích hợp telemetry
đó trên baseline 0.4.18 hoặc mới hơn, kiểm chứng tương thích, build/deploy bằng quy trình
riêng và kiểm tra start/refresh/submit/reset thực tế. Không hạ plugin xuống gói 0.4.17.
CMS-AI merge không xác nhận LMS đã chạy telemetry mới. Timer guard và native grading phải
được kiểm chứng sau rollout; không thay LMS plugin bằng bundle cũ trong CMS-AI.

Theo dõi thời gian batch, CPU/RSS, queue wait và các count SCORED/INSUFFICIENT_DATA/ERROR.
Vượt giới hạn nguồn cần đánh giá partition/cohort tiếp theo; không giảm ngưỡng hoặc bỏ cap.
Kiểm tra tài khoản giảng viên chỉ xem lớp được phân công, không thấy tên tham chiếu ngoài lớp.

## Đánh giá offline tái lập

Từ repo root, Python đã cài `backend/requirements-ci.txt`:

```sh
python scripts/evaluate-learning-ml.py --audit /path/to/export-dir --output /tmp/ml-report.json --seed 42
python scripts/evaluate-learning-ml.py --benchmark 1000 --output /tmp/ml-1000.json
python scripts/evaluate-learning-ml.py --benchmark 5000 --output /tmp/ml-5000.json
```

CLI đọc `learning.json`, không mở DB/production connection, không sửa archive hoặc fabricate
version. Không cho output trùng input. Nhiều export cùng class được chọn bản mới nhất;
cohort vẫn tách course/content, dedup student. Source bị truncated không được âm thầm scored.
Output chỉ số tổng hợp và hash, không username/đáp án/danh sách điểm cá nhân.

Replay archive ngày 07/10 trong phiên 16/10:

| Mục | Kết quả |
|---|---:|
| Lớp / sinh viên roster khác nhau | 3 / 83 |
| Người đủ đặc trưng video | 31 |
| Người thiếu tối thiểu ba video đo hợp lệ | 52 |
| Nhóm đủ 50 người để score | 0 |
| Quiz đủ provenance server / được score | 0 / 0 |
| Nhóm user/unit quiz thiếu provenance | 5.195 |
| Số kết quả ML thực tế đã chấm | 0 |

Một video có measurement không hợp lệ; reason counts có thể chồng nhau, không cộng thành
số sinh viên. Export danh sách lớp không có scope được bỏ qua. Hash official learning
snapshots trước/sau đều `eb8c6daa427dd1a8f3f79109c0ed3677579b78d5ded25cc713844efe447bb21c`.
Đây là hash dữ liệu export được đọc, không phải xác nhận DB production đã chạy recalculation.
Không có nhãn nên disagreement với luật chỉ là mô tả; hiện 0 trường hợp đủ điều kiện so sánh.

Benchmark synthetic, process mới cho từng cỡ (bao gồm import/model memory), Linux x86_64,
Python 3.12.14, 9 logical CPUs hiển thị, một model thread:

| Rows | Thời gian tổng | Incremental peak RSS | Budget thử nghiệm |
|---|---:|---:|---|
| 1.000 | 0,7249 giây | 115,46 MiB | Đạt <10 giây / <256 MiB |
| 5.000 | 0,9347 giây | 122,37 MiB | Đạt <10 giây / <256 MiB |

RSS dùng ru_maxrss của Linux, baseline trước tạo features/import sklearn. Không phải SLO
production và chưa gồm DB I/O, concurrent jobs hoặc memory của worker đã nạp toàn app.
Cần đo lại trên worker thật và dữ liệu đại diện trước khi mở rộng pilot.

## Hai đợt quan sát và rollback

Sau deploy, thu ít nhất hai đợt telemetry. Lấy mẫu ngẫu nhiên cả nhóm flagged và unflagged
cho giáo viên xác minh, ghi sample size và lý do xác nhận. Cần đủ nhãn và split theo
student/course/đợt học để tránh leakage trước khi đo precision/recall hoặc học có giám sát.
Không tự động đổi điểm, khóa học hay xử lý kỷ luật dựa trên ML v1.

Quay lui: đặt `ANALYTICS_ML_MODE=off` trên backend/worker, áp dụng lại process, rồi kiểm tra
API trả DISABLED, drawer không hiện cờ ML cũ, pipeline luật/official grades vẫn hoạt động.
Không cần migration hoặc xóa evidence. Deployment, pilot, nhãn giáo viên và rollback runtime
chưa được thực hiện trong phiên phát triển này; kết quả đó phải ghi riêng sau khi có bằng chứng.
