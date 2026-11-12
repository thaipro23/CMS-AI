# Một AP key, cô lập lỗi daily và nhận định video — 12/11/2026

Baseline nguồn: `9164170e3507782a033f8fc28d4c163490673635`.
Đầu vào sự cố: daily root `a687bbda-c9e6-4620-b3c7-d70d3d8c50b7` báo
course_mapping exhausted ở PTCĐ/kỳ `c75c7339-c22a-4413-bcce-9a5bdc365063`, môn
PSY1013 không tìm được đúng một course CMS. Ví dụ analytics của datntpy00232
có nhiều video gần hoàn thành, thời gian xem ước tính thấp, nhưng NORMAL/
NO_ACTION ở điểm bất thường 35. Đây là dữ liệu người vận hành cung cấp, không
phải kết quả truy vấn production của phiên này.

## Hành vi sau sửa

### AP dùng một key

AP chỉ gửi `X-AP-API-Key`; không cần Client ID. Key dùng chung các hệ/cơ sở
được cấp trong `AP_ANALYTICS_CONFIG_JSON` (digest SHA-256 + scopes). Scope vẫn
được enforce ở backend. Config clients cũ chỉ được chấp nhận khi đúng một
client; nhiều key fail closed để buộc chuyển cấu hình rõ ràng. Config mới sai
không fallback. [Contract và cách cấp key](../AP_LEARNING_RESULTS_API.md).

### Daily giữ lỗi tại dependency

Bulk map đã có mapped_class_ids/failed_class_ids và subject_results; coordinator
cũ rút gọn thành một lỗi branch/term rồi `_fail_exhausted_stage` dừng root và
các parent chưa hoàn tất. Nay coordinator lưu failure_details/blocked class IDs,
giữ thành công qua retry và xử lý tiếp các target không phụ thuộc lỗi.

- Retry mapping chỉ chọn phần chưa thành công; không làm lại lớp đã map tốt.
- Result partition thiếu/sai/ngoài frozen scope không đủ căn cứ để cho lớp đi
  tiếp. Không chọn course đầu tiên, không tự map PSY1013 khi course mơ hồ/thiếu.
- Lớp lỗi mapping không đi enroll/score; lớp độc lập vẫn được xử lý. Lỗi AP,
  account/enrollment, scoring và các stage report cũng giữ đúng phạm vi phụ thuộc.
- Workbook cơ sở cần đủ các lớp trong phạm vi gốc. Cơ sở bị thiếu dependency
  không xuất workbook như thể đầy đủ; cơ sở lành vẫn xuất. HO chỉ tạo khi có
  đầy đủ tập báo cáo cơ sở yêu cầu. Lý do skip được giữ để đối soát.
- Root có lỗi vẫn kết thúc failed kèm processing_complete/partial_success và
  failure_details; không biến xử lý một phần thành thành công toàn bộ.

Job đã failed vì business stage_retry_exhausted không tự hồi sinh sau deploy.
Retry API hiện có chỉ dành subject_auto_map_all_sync; recovery daily chỉ dành
lỗi continuation dispatch/recovery. Không sửa trực tiếp DB để đổi status/attempt.
Bản sửa áp dụng root đang chạy hoặc root mới; root terminal cùng ngày vẫn được
trả về theo idempotency. Có thể theo dõi lần lịch mới sau deploy và xử lý mapping
PSY1013 thủ công đúng scope bằng giao diện hiện có. Không tự chạy recovery ở đây.

### Video và tên dấu hiệu

Điểm bất thường là trọng số tín hiệu, không phải xác suất. Trọng số video tối
đa45 nên điểm35 không chạm ngưỡng70. Escape hatch trước còn yêu cầu trung bình
hoàn thành toàn course>=90 và tỷ lệ video nghi vấn>=80%; video khác làm loãng
bằng chứng từng video. Trường hợp lặp lại có đủ phép đo nay được review khi có
ít nhất3 video hoàn thành>=90% nhưng xem<25%, trải trên ít nhất2 Bài/session
và đủ hoạt động theo classifier. Không cần chờ thêm tín hiệu Quiz để đạt70.

Chỉ dùng thời gian có căn cứ: duration biết được, playback history đủ, khoảng
phát được quan sát/seek đủ điều kiện. Timing thiếu, history không đầy đủ/không có marker `resume_continuity_checked`
hợp lệ (trừ khi các segment vị trí còn giữ đủ căn cứ) hoặc
chỉ một đoạn resume sát cuối không được coi là bằng chứng xem0. Tôn trọng media
advancement đã đo để tránh flag nhầm do estimator cũ bị thiếu. Chất lượng thấp
và reason MISSING_WATCH_TIMING thể hiện hạn chế. Không kết luận gian lận.

Quy tắc hiện hành: `learning_behavior_audit_v3`. Snapshot cũ/không biết version
được đánh dấu stale + snapshot_recompute_required + BEHAVIOR_RULES_UPDATED;
GET giữ kết quả lịch sử, không ghi hay tự reclassify. UI yêu cầu tính lại thay vì
đề xuất “Không cần xử lý” từ quy tắc cũ. AP summary cũng đếm snapshot này là stale,
chỉ đọc version JSON scalar, không tải/trả evidence hoặc đáp án.

| Reason code giữ nguyên trong API | Tên hiển thị |
|---|---|
| LARGE_SEEK_JUMP | Tua video qua một đoạn dài |
| HIGH_COMPLETION_LOW_WATCH_TIME | Video gần hoàn thành nhưng thời gian xem rất ít |
| MANY_VIDEOS_COMPLETED_TOO_FAST | Nhiều video hoàn thành quá nhanh so với thời lượng |
| QUIZ_BEFORE_VIDEO | Làm Quiz trước khi xem video |
| DEADLINE_PATTERN_MATCHED | Hoạt động học khớp mốc thời hạn |
| WATCH_THEN_ATTEMPT_PROBLEM | Có xem video trước khi làm Quiz |
| REPEATED_HIGH_COMPLETION_LOW_WATCH | Lặp lại việc hoàn thành video với thời gian xem rất ít |

Deadline khớp và có xem trước Quiz là ngữ cảnh/trình tự, không tự là bất thường.
Hai trang Student Management và Analytics dùng chung resolver tên; không cắt
còn4 lý do trong Bài. Điểm hiển thị /100; thời gian dưới phút dùng giây, phân biệt
0 với chưa có dữ liệu. Nhãn là hiển thị, không đổi machine code API.

## Sau build/deploy

1. Rollout backend và các worker từ cùng nguồn mới; rollout frontend.
2. Cấp một shared key vào AP backend, digest/scopes vào Secret API deployment.
   Dùng đúng campus code và AP IDs; smoke test key đúng/sai, cặp scope cho phép/cấm.
3. Dùng nút tính lại phân tích học online của lớp (job worker; force khi cần)
   rồi đối chiếu snapshot version, timing evidence, nhận định và lý do. Không dùng
   cập nhật điểm hoặc reset Quiz thay cho recalculation analytics.
4. Nếu log gốc đã qua retention và video measurement không đủ lịch sử, không thể
   khôi phục bằng cách đổi nhãn. Cần thể hiện thiếu dữ liệu; replay chỉ khả thi
   khi còn raw events hợp lệ. GET không tự đọc lại raw tracking.
5. Theo dõi daily root mới: đối chiếu lớp lành vẫn enroll/score, lỗi PSY1013 còn
   trong failure_details, báo cáo cơ sở/HO đủ điều kiện mới được xuất.

Không có migration, flush Redis, sửa PVC, đổi trạng thái production hoặc triển
khai K8s trong phiên này. Kiểm thử SQLite/local không chứng minh lock/latency
PostgreSQL, broker delivery hay dữ liệu AP thật; cần nghiệm thu sau rollout.
