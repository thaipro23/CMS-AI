# Thiết kế ML cho analytics học tập — thiết kế đã duyệt

Trạng thái: Thái đã duyệt và yêu cầu viết code ngày 09/10; source/kiểm chứng hiện tại xem [runbook](../../LEARNING_ANALYTICS_ML_ROLLOUT.md). Yêu cầu đã có: bổ sung học máy và sau khi kiểm chứng merge CMS-AI vào `feat/import-quiz-cms-old-su26`. Việc merge CMS-FPT hoặc triển khai production chưa nằm trong yêu cầu merge này.

## Mục tiêu và phạm vi

Thêm một kết quả học không giám sát để nhận diện hành vi khác biệt so với nhóm tham chiếu tương đương. Phiên bản đầu dùng Isolation Forest trong worker analytics hiện tại, chạy theo batch; không tạo dịch vụ ML riêng. Kết quả ML hiển thị riêng trong phần bằng chứng của sinh viên, không thay điểm học tập, phân loại hiện tại hoặc tự kết luận gian lận.

Không dùng các nhãn NORMAL/POSSIBLE_ANOMALY do luật hiện tại tạo ra làm nhãn huấn luyện đúng/sai. Chưa có tập nhãn giáo viên xác nhận, vì vậy chưa xây mô hình có giám sát hoặc công bố precision/recall/accuracy thực tế. Mẫu bất thường có thể là sinh viên học tốt, đổi cách học hoặc lỗi telemetry.

## Hai họ đặc trưng

**Video:** completion/watch gap, watch ratio, seek count per counted watch minute, passive watch ratio. Tính từ các video có duration hợp lệ và mapping đúng; cần ít nhất 3 video đo được. Tổng hợp có trọng số duration, giới hạn ratio trong miền hợp lệ và không coi dữ liệu thiếu là số 0. Ngữ cảnh so sánh gồm course, fingerprint bộ video của outline và khoảng mức tiếp xúc nội dung: 3–5, 6–10, từ 11 video. Đặc trưng là tổng hợp tích lũy ở thời điểm tính, không giả vờ là cửa sổ 7/30 ngày khi nguồn không có dữ liệu theo cửa sổ.

**Quiz:** seconds per independent submission, successful reset count per persisted attempt, submission count per comparable response. Chỉ dùng start/reset có provenance server, phiên bản và question identity hợp lệ. Cần ít nhất 6 thời điểm nộp độc lập; bỏ burst nộp toàn form và timeout khỏi đặc trưng tốc độ. Nhóm tham chiếu cùng course, quiz vertical và fingerprint tập response/version tương đương; các đề ngẫu nhiên không có nhóm đủ tương đương sẽ được bỏ qua. Không dùng điểm chính thức làm nhãn gian lận. Nếu chỉ đủ dữ liệu video thì chỉ chạy ML video, và ngược lại.

Các thiếu hụt có mã riêng: MISSING_VIDEO_DURATION, MISSING_SESSION_MAPPING, UNTRUSTED_QUIZ_SESSION, MISSING_CONTENT_VERSION, MISSING_QUESTION_IDENTITY, INSUFFICIENT_INDEPENDENT_TIMING, BASELINE_TOO_SMALL, CONSTANT_FEATURES. Log cũ không được gán phiên bản từ nội dung hiện tại.

## Mô hình và phạm vi tham chiếu

Mỗi nhóm có ít nhất 50 sinh viên khác nhau có đặc trưng hợp lệ mới được fit. Mức 50 là chính sách khởi đầu để giảm việc fit trên lớp rất nhỏ, không phải bảo đảm độ chính xác; cấu hình có thể tăng nhưng không thấp hơn 50 trong bản đầu. Đếm unique canonical username, không đếm số event/lượt làm. Với quiz, chọn lượt hợp lệ đầu tiên cho mỗi sinh viên ở nhóm đó để tránh người reset nhiều được tính nhiều mẫu. Video dùng một hàng tổng hợp cho mỗi sinh viên/course/context. Trùng sinh viên ở nhiều lớp không tạo mẫu tham chiếu trùng.

Giới hạn 5.000 mẫu/nhóm, lấy mẫu theo thứ tự hash ổn định để không phụ thuộc thứ tự DB; ưu tiên fairness thay vì username order. Không fit nếu mọi feature đều hằng số. `IsolationForest(n_estimators=100, max_samples=min(256, n), contamination='auto', random_state=42, n_jobs=1)` chạy trên ma trận finite. Không ấn định một tỷ lệ sinh viên phải bị gắn cờ. Kết quả outlier dùng `decision_function < 0`; lưu `-score_samples` và percentile so với nhóm, không gọi chúng là xác suất gian lận.

Đây là outlier detection trên batch hiện tại, chưa phải mô hình dự đoán được huấn luyện trên lịch sử chuẩn rồi áp vào sinh viên mới. Không hứa phát hiện nhóm gian lận chiếm đa số: nếu hành vi xấu trở thành phổ biến, mô hình có thể coi là bình thường; luật bằng chứng vẫn cần giữ để đối chiếu.

## Tích hợp và lưu trữ

Gắn feature builder và batch scorer sau bước tính luật hiện tại. Fit một lần/nhóm trong worker, không fit ở GET dashboard, không fit mỗi sinh viên. Khi tính riêng một username vẫn dựng nhóm tham chiếu đủ phạm vi, nhưng chỉ ghi kết quả của username được yêu cầu. Thêm guard giới hạn dữ liệu và kiểm tra cancellation trước mỗi nhóm để không chiếm worker vô hạn.

Lưu kết quả mới vào `AnalyticsLearningBehaviorSnapshot.evidence_json['ml']` cho video và `AnalyticsQuizIntegrityResult.evidence_json['ml']` cho quiz. Không cần migration cho bản đầu. Kết quả gồm family, status, algorithm, model/feature version, cohort digest, unique reference count, cutoff, calculated_at, features, raw anomaly score, reference percentile, outlier và ba độ lệch lớn nhất so với median nhóm. Độ lệch này chỉ là mô tả thống kê, không phải giải thích nhân quả hoặc feature attribution của Isolation Forest. Không lưu tên/đáp án của người tham chiếu trong kết quả trả cho giáo viên.

Raw tracking tiếp tục giữ 3 ngày theo chính sách hiện tại. Các aggregates và kết quả ML dùng cơ chế lưu hiện tại nên vẫn đọc được khi raw log bị dọn. Snapshot bị ghi đè khi tính lại; bản đầu không có kho lịch sử ML. Báo cáo đánh giá offline được xuất riêng, và kế hoạch huấn luyện theo thời gian sau này cần thiết kế kho feature lịch sử riêng.

Config: `ANALYTICS_ML_MODE=off|shadow`, mặc định off; `ANALYTICS_ML_MIN_REFERENCE_STUDENTS=50`; `ANALYTICS_ML_MAX_REFERENCE_STUDENTS=5000`; `ANALYTICS_ML_PILOT_CLASS_IDS` rỗng nghĩa không có lớp pilot. Shadow chỉ chạy trong lớp được chỉ định. API chỉ trả kết quả latest khi model/feature version, cutoff và scope hợp lệ. Lỗi fit/import/nguồn dữ liệu ghi status ERROR hoặc INSUFFICIENT_DATA theo nguyên nhân, không chặn pipeline tính điểm. Tắt tính năng trả DISABLED thay vì dùng lại cờ ML cũ.

## UI và đánh giá

Drawer hiện tại thêm thẻ “Phân tích học máy” với nhãn “Khác biệt so với nhóm tham chiếu”, số người tham chiếu, thời điểm tính, trạng thái dữ liệu và độ lệch được quan sát. Dùng một chỉ số riêng, không gộp vào suspicious_score hoặc confidence_score. Không hiển thị phần trăm xác suất gian lận. Giữ quyền teacher/class scope hiện tại và không lộ sinh viên ngoài phạm vi.

Kiểm thử synthetic chỉ chứng minh plumbing/tính ổn định, không chứng minh phát hiện gian lận thực tế. Replay audit 83 sinh viên để kiểm tra thiếu dữ liệu, tính toàn vẹn điểm và số mẫu hợp lệ. Nếu không nhóm nào đạt điều kiện thì báo đúng zero scored, không giảm ngưỡng để có kết quả đẹp. Sau deploy shadow, giáo viên xem một mẫu được đánh dấu và một mẫu không đánh dấu. Chỉ các nhãn đã xác nhận mới được dùng để báo cáo precision/recall hoặc cân nhắc học có giám sát; lấy mẫu ngẫu nhiên và tách sinh viên/course/đợt học phù hợp để tránh leakage.

## Merge, pilot và quay lui

Implement trên nhánh riêng từ head đã kiểm thử của PR #13, đưa toàn bộ audit fix và ML vào nhánh đích CMS-AI sau khi rebase/update với code mới và CI xanh. Kiểm tra expected head SHA trước merge; không force push nhánh đích. ML mặc định off cho lần merge đầu. Production rollout là bước sau merge: bật shadow cho lớp pilot đủ dữ liệu, kiểm tra CPU/RAM/queue và kết quả giáo viên. Quiz ML cần CMS-FPT 0.4.17 được merge/build/deploy bằng quy trình riêng và xác nhận telemetry runtime; có mã plugin trong PR không đồng nghĩa LMS đã chạy mã đó.

Quay lui bằng `ANALYTICS_ML_MODE=off`, giữ pipeline luật và điểm chính thức hoạt động; xác nhận API/UI không hiện cờ cũ như đang hoạt động. Chưa thêm chế độ tự động điều chỉnh nhãn/kỷ luật sinh viên.
