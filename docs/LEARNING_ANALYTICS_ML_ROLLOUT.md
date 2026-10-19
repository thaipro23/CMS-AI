# Video relative ranking v2: vận hành và kiểm chứng

Baseline CMS-AI: `dbd0c62`, cập nhật 19/10/2026 (Asia/Ho_Chi_Minh).
Thiết kế [video v2](superpowers/specs/2026-10-19-video-relative-ranking-design.md)
thay thế phần video của thiết kế ML v1. Điểm biểu thị thứ hạng tương đối của
chênh lệch hành vi đo được; không có nhãn kết tội hoặc xác suất vi phạm.

## Luồng và số đo

LMS tracking → materialize PostgreSQL → worker batch → evidence JSON → API đọc →
drawer giảng viên. Redis giữ chức năng queue/cache hiện có; không có dịch vụ ML,
migration hay model registry mới. GET không fit mô hình; điểm chính thức và kết quả
luật giữ nguyên. Snapshot/evidence chỉ giữ kết quả ML mới nhất.

`video_playback.py` lưu `playback_measurement` độc lập với tổng wall-time của luật.
Đo tiến trình nội dung từ vị trí và thời gian giữa các sự kiện phát/dừng/tua;
hỗ trợ tiến trình quan sát tới 4x (có dung sai vị trí 2 giây), loại bước nhảy tua.
Giữ trạng thái giữa các batch; phân biệt sự kiện cùng timestamp và replay đúng
sự kiện. Thiếu phát đầu, bắt đầu quan sát giữa video, mất vị trí hoặc lịch sử
cộng dồn cũ thiếu số đo mới đều không đủ để xếp hạng. Không bịa tốc độ lịch sử.
Marker timestamp của materializer giữ tối đa 1.000 event IDs; vượt trần hoặc
quá 128 chữ ký sự kiện cùng thời điểm làm lịch sử ML không hoàn chỉnh.

Tốc độ quan sát là tiến trình nội dung / thời gian đo được, chỉ để giải thích,
không phải tốc độ người học chọn trên player. Các đặc trưng xếp hạng:
coverage/độ dài; hoàn thành trừ coverage; số tua/phút nội dung; tỷ lệ media thụ động.
Người xem 1x và 2x có cùng tiến trình nội dung nhận cùng đặc trưng. Coverage bằng
0 có đo được khác với thiếu đo lường. Cần ít nhất ba video hợp lệ, định danh chính
xác trong outline đang hoạt động. Feature tích lũy tại cutoff, không phải cửa sổ
7/30 ngày. Raw staging có retention 3 ngày; dữ liệu tổng hợp vẫn tồn tại.

## Nhóm tham chiếu

- Tối thiểu 30 người khác nhau; 30–49 hiện “Độ tin cậy thấp”; 50+ là STANDARD.
  Đây là chất lượng cỡ mẫu, không xác nhận mô hình đúng. Có thể tăng minimum.
- `ANALYTICS_ML_VIDEO_REFERENCE_COURSE_IDS` là danh sách course ID cho phép, cộng
  course đang tính; tối đa 20 course. Rỗng: chỉ course đang tính. Chọn các khóa có
  bối cảnh phù hợp trước pilot; không quét/gộp tự động toàn hệ thống.
- Chỉ roster active và effective class/course mapping; gom video hợp lệ của một
  người trong pool, đếm người đó một lần. Nhóm theo số video 3–5 / 6–10 / 11+ và
  trung vị độ dài ≤5 / ≤20 / >20 phút. API không lộ tên người/khóa tham chiếu.
- Mỗi nhóm lấy tối đa 5.000 người theo hash ổn định; cap 20.000 roster entries và
  50.000 source rows/table. Vượt cap là lỗi bổ sung, không cắt âm thầm rồi chấm.
- Tính riêng một sinh viên vẫn dùng toàn reference pool nhưng chỉ ghi target.
  Savepoint, row lock và snapshot/cutoff guards bảo vệ transaction và job chạy chồng.
  Kiểm tra tắt/hủy giữa các lần đọc nguồn và trong vòng build; cấu hình pool đổi
  trong lúc fit không được xuất bản evidence mang scope sai.

## Median/MAD và mô hình đối chiếu

Median/MAD là điểm chính: scale=max(1.4826×MAD, floor), floor=0,05 cho tỷ lệ
và 1 cho số tua/phút nội dung. Gap xét chiều tăng, coverage xét chiều giảm;
seek/passive xét độ lệch hai chiều. Điểm thô là đóng góp chuẩn hóa lớn nhất.
Percentile dùng midrank, cùng điểm nhận cùng thứ hạng; nhóm hoàn toàn hằng số
không bị ép tạo thứ hạng. Bảng hiển thị số đo, median, MAD và các đóng góp lớn nhất.

Isolation Forest đối chiếu: 200 cây, max_samples≤256, seed mặc định 42,
contamination auto, một model thread. Gần nhau khi Spearman≥0,8 và overlap top 5
có xét ties≥80%. Khi gần nhau chỉ trình bày cách giải thích median/MAD; khi khác
nhau hiện thêm percentile đối chiếu. Lỗi forest vẫn giữ baseline hợp lệ và hiện
trạng thái đối chiếu chưa sẵn sàng. Không dùng độ lệch MAD làm attribution nhân
quả của forest. Runtime pin: NumPy2.2.1, sklearn1.6.1, SciPy1.15.1,
joblib1.4.2, threadpoolctl3.5.0.

## Cấu hình bật, tắt và quiz

```dotenv
ANALYTICS_ML_MODE=off
ANALYTICS_ML_PILOT_CLASS_IDS=
ANALYTICS_ML_VIDEO_ENABLED=true
ANALYTICS_ML_QUIZ_ENABLED=false
ANALYTICS_ML_VIDEO_REFERENCE_COURSE_IDS=
ANALYTICS_ML_MIN_REFERENCE_STUDENTS=30
ANALYTICS_ML_MAX_REFERENCE_STUDENTS=5000
```

Deploy backend, worker-analytics và frontend cùng source. Cấu hình pool phù hợp,
đặt mode=shadow và pilot class IDs cụ thể, giữ quiz=false, áp dụng cấu hình lên
các process rồi dùng chức năng tính lại lớp hiện có. Không tự bật khi pilot rỗng.

Tắt: mode=off, hoặc VIDEO_ENABLED=false cho riêng video; áp dụng cấu hình/restart
backend và worker. Env không tự cập nhật process đang chạy. Sau khi áp dụng, API
trả DISABLED và ẩn cả điểm đã lưu; không cần xóa evidence hoặc migration.
Kiểm tra source/fit/write có checkpoint nhưng không ngắt một SQL đang thực thi.

Quiz giữ tắt. Điều kiện tương lai: telemetry của CMS-FPT PR #3 (gói cũ 0.4.17)
được port và deploy tương thích trên plugin 0.4.18 hoặc mới hơn; kiểm chứng
start/refresh/submit/reset, phiên bản đề và timing server; đủ người và sáu mốc
nộp độc lập hợp lệ. Không hạ plugin xuống 0.4.17. Source CMS-FPT quan sát ngày
16/10 chưa có telemetry đó; CMS-AI merge không xác nhận LMS đã triển khai.

## Replay và benchmark tái lập

```sh
python scripts/evaluate-learning-ml.py --audit /path/to/exports --output /tmp/video-replay.json
python scripts/evaluate-learning-ml.py --benchmark 1000 --output /tmp/video-1000.json
python scripts/evaluate-learning-ml.py --benchmark 5000 --output /tmp/video-5000.json
```

Replay mặc định video-only; pool giới hạn trong các export người vận hành cấp.
Chọn export mới nhất mỗi lớp, dùng outline mới nhất mỗi course để lọc cả export
cũ; snapshot outline đồng thời mâu thuẫn/truncated không được chấm. Nhóm quiz
bị bỏ qua được chuẩn hóa alias về vertical. `--include-quiz` chỉ chẩn đoán offline,
không bật quiz runtime. Output chỉ counts/digest/lý do, không tên hay đáp án.
Không ghi đè input. Chưa có nhãn giảng viên để đo accuracy/precision/recall.

Replay archive 07/10 trong phiên 19/10: 3 lớp / 83 người; 0 người đủ video v2,
0 nhóm được chấm. Cả 83 thiếu ba video đo hợp lệ; trong đó 38 có video legacy
thiếu playback measurement, một trường hợp có measurement không hợp lệ
(reason counts chồng nhau). 5.195 nhóm người/quiz chuẩn hóa giữ tắt. Hash official export trước/sau:
`eb8c6daa427dd1a8f3f79109c0ed3677579b78d5ded25cc713844efe447bb21c`.
Đây là kiểm tra export đọc-only, không phải xác nhận DB production đã tính lại.

Benchmark synthetic process mới, Linux x86_64/Python3.12.14, 9 logical CPUs,
một model thread, gồm first import, chưa gồm DB I/O/concurrent app worker:

| Người | Tổng giây | Incremental peak RSS | Budget test |
|---|---:|---:|---|
| 1.000 | 0,9252 | 110,84 MiB | <10s / <256MiB: đạt |
| 5.000 | 1,1019 | 123,51 MiB | <10s / <256MiB: đạt |

Năm seed 0,1,7,42,99: trên fixture 300 người tham chiếu và năm người giả lập
hoàn thành gần 100%/coverage rất thấp (seek/passive vẫn trong vùng thông thường),
top 5 của cả hai cách trùng đủ năm người; mọi cặp seed overlap 100%≥80%.
Kết quả synthetic không chứng minh độ chính xác hoặc ổn định trên mọi cohort.

## Kiểm chứng và trạng thái

116 focused backend tests, 28 frontend unit/rendered tests, 35 Playwright tests
đạt; frontend lint/typecheck/production build và fatal Ruff/compile đạt.
Review độc lập phát hiện và đã có regression cho sự kiện cùng timestamp, thiếu
phát đầu, dừng đọc khi disable và nhất quán outline replay. Không hoãn minor.

Full backend có 312 lỗi nền được ghi trong
[baseline](fixes/LEARNING_ML_TEST_BASELINE_2026-10-16.txt); đối chiếu tập tên lỗi
trên source sạch, không sửa/bỏ assertion lịch sử để tạo suite xanh.
PostgreSQL/Redis, migration, concurrency và image/Compose là gate CI đúng PR head.
Trạng thái CI/merge xem PR từ nhánh `feat/video-learning-ranking-20261019`.
CHƯA DEPLOY / CHƯA BẬT PILOT / CHƯA ĐO PRODUCTION trong phiên phát triển này.

Sau deploy, thu số đo mới và hai đợt quan sát; theo dõi latency/RSS/queue/counts,
lấy mẫu giảng viên xác minh, gồm cả phần thấp và cao của bảng xếp hạng.
Dữ liệu cũ thiếu lịch sử không tự trở thành đủ chỉ vì hạ ngưỡng từ 50 xuống 30.
