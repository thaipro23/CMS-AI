# CONTEXT v25.9.16.5.86 — StudentModule Progress Fallback + Active Connector Diagnostics

Bản mới nhất nên dùng: `v25.9.16.5.86-studentmodule-progress-fallback`.

## Lý do ra bản này

AI Server hiển thị `Course completion = N/A` dù Django shell LMS đọc được StudentModule completion:

```text
completed_blocks=15
total_blocks=70
```

Sau Đồng bộ full CMS, DB vẫn lưu:

```text
completed_blocks=NULL
progress_percent=NULL
raw_json.progress={}
```

Kết luận nghiệp vụ/kỹ thuật: cần kiểm tra đường HTTP connector active trên LMS, restart LMS nếu đang cache connector cũ, và sửa connector/backend để StudentModule fallback không bị bỏ rơi.

## Thay đổi chính

### 1. Connector LMS có version active

Trong `openedx_ai_connector.student_insight` thêm:

```python
CONNECTOR_VERSION = '25.9.16.5.86'
```

`class-analytics` diagnostics trả thêm:

```text
connector_version
active_http_namespace
student_module_model_available
student_module_model_source
student_module_fallback_enabled
student_module_progress_ratio_enabled
```

### 2. Connector luôn merge StudentModule counts

Trước v86, StudentModule fallback chỉ chạy khi không có result nào. Nếu Course Home/BlockCompletion tạo bucket rỗng/không percent, StudentModule có thể không được dùng đúng.

v86 sửa thành:

- luôn đọc StudentModule counts nếu model có sẵn.
- lưu `student_module_completed_blocks`.
- lưu `has_student_module_fallback`.
- nếu thiếu Course Home percent nhưng có total blocks thì set:

```text
progress_source = StudentModule
progress_percent = completed_blocks / total_blocks * 100
```

Ví dụ:

```text
15 / 70 * 100 = 21.43%
```

### 3. Backend AI Server chấp nhận StudentModule fallback

Backend không còn chỉ nhận Course Home Progress official. Accepted progress sources gồm:

- `CourseHomeProgressRoute:completion_summary`
- `CompletionAPI:*`
- `StudentModule`

Nhưng vẫn không đoán từ quiz/grade/detailed grades.

### 4. Backend lưu đủ snapshot

`_upsert_learning_snapshot()` lưu:

```text
completed_blocks
total_blocks
progress_percent
raw_json.payload.progress_source
raw_json.payload.progress
learning_diagnostics.student_module_progress
```

### 5. UI chẩn đoán rõ hơn

Màn chi tiết lớp hiển thị thêm:

- `StudentModule fallback: x/y`
- Course completion TB có cả official count và StudentModule count.
- từng sinh viên hiển thị `Nguồn: StudentModule fallback` nếu đang dùng fallback.

## Quy tắc không đổi

- **Đồng bộ full CMS** vẫn check/tạo user, enroll, rồi lấy progress/điểm.
- **Cập nhật điểm** vẫn chỉ đọc progress/điểm, không tạo user, không enroll.
- Không dùng quiz/grade để đoán Course completion.
- StudentModule fallback chỉ dùng khi connector trả rõ nguồn `StudentModule` và có `completed_blocks/total_blocks`.

## Kiểm tra bắt buộc sau deploy

1. LMS import connector phải in `CONNECTOR_VERSION=25.9.16.5.86`.
2. Backend gọi HTTP connector phải thấy diagnostics có `connector_version=25.9.16.5.86`.
3. HTTP result cho SV test phải có `progress_source=StudentModule`, `completed_blocks`, `total_blocks`, `progress_percent` nếu Course Home official không trả.
4. Sau Cập nhật điểm, DB snapshot không còn null ở `completed_blocks/total_blocks/progress_percent` với SV có StudentModule.
