# Batch 16 — Cross-layer Workflow Integrity Audit

## Phạm vi

Audit và sửa xuyên suốt Frontend → FastAPI → SQLAlchemy → Celery → Open edX connector/plugin cho các workflow có rủi ro cao:

1. Cập nhật danh mục cơ sở.
2. Đồng bộ AP.
3. Map Course CMS và tạo Quiz/Final test trên Open edX.
4. Chốt Release và publish/public bộ đề sang Open edX Library.
5. Đồng bộ course tree dùng làm dữ liệu dự phòng.

Baseline đầu vào: `v25.9.16.7.2.64.16.5.7.2.3` cộng các batch UI/API trước đó. Batch này không thêm migration và không thay đổi route công khai.

## 1. Root cause của lỗi Course Blocks HTTP 400

Request lỗi chứa:

```text
course_id=course-v1:FPT+COM1071+SU26/
```

Dấu `/` cuối làm Course Blocks API nhận một course key không canonical. Course ID trước đây được trim đơn giản ở nhiều tầng, vì vậy cùng một course có thể tồn tại dưới hai dạng:

```text
course-v1:FPT+COM1071+SU26
course-v1:FPT+COM1071+SU26/
```

Hậu quả:

- Open edX trả 400 khi parse CourseKey.
- Mapping và dữ liệu sync cũ có thể không được tìm thấy do so sánh chính xác chuỗi.
- UI suy luận sai rằng từng Bài không có Section, dù nguyên nhân thật là toàn bộ cây course chưa đọc được.
- Lịch sử Quiz có thể bỏ sót bản ghi legacy có dấu `/`.

### Cách sửa

Tạo một boundary canonical dùng chung:

```python
normalize_openedx_course_id(...)
openedx_course_id_candidates(...)
```

Boundary chấp nhận:

- Course key chuẩn.
- Course key URL-encoded.
- Studio/LMS URL có chứa Course key.
- Course key có dấu `/` thừa.

Giá trị ghi mới luôn là:

```text
course-v1:ORG+COURSE+RUN
```

Khi đọc dữ liệu legacy, query đồng thời canonical và dạng có `/`.

Áp dụng tại:

- Question Bank course mapping.
- Academic course mapping.
- Course sync/clean-resync.
- Course Blocks connector.
- Mọi mutation connector tạo/xóa Quiz, timer, ItemBank và publish OLX.
- Studio connector plugin.
- Student insight plugin.
- Lịch sử CourseQuizInstance.

## 2. Tạo Quiz trên Open edX

### 2.1. Đọc cây course có fallback có kiểm soát

Luồng mới:

```text
Studio connector
→ Course Blocks API đầy đủ
→ Course Blocks API structural, bỏ student_view_data
→ Course Blocks API tối thiểu
→ CourseSyncState đã lưu trong AI Server
```

Các profile giảm dần giúp tương thích với deployment Open edX không hỗ trợ đủ `requested_fields` hoặc `student_view_data`.

401/403 không retry bằng profile khác vì đây là lỗi xác thực/phân quyền. Các lỗi cấu trúc request hoặc khác biệt deployment mới dùng profile tiếp theo.

### 2.2. Không báo sai “Thiếu Section” cho từng Bài

Khi toàn bộ cây course không đọc được và không có cache:

- Chỉ trả một blocker toàn cục `COURSE_TREE_UNAVAILABLE`.
- Không tạo một lỗi “không tìm thấy Section” cho từng Bài.
- Mỗi dòng hiển thị `Chưa đọc được cây Course CMS`, không khẳng định Section không tồn tại.
- `Thiếu Section` không được cộng vào KPI khi chưa đủ dữ liệu để kết luận.

Khi có `CourseSyncState`, UI hiển thị rõ nguồn là dữ liệu sync cũ và vẫn cho map nếu dữ liệu đủ.

### 2.3. Mapping và lịch sử tương thích dữ liệu cũ

- Mapping cũ có dấu `/` được tìm lại bằng candidate query.
- Khi lưu/apply, mapping được migrate sang canonical.
- Lịch sử Quiz lọc bằng cả canonical và legacy form.
- Frontend normalize Course ID trước preview, apply và tải lịch sử.

### 2.4. Rollback khi tạo Quiz dở dang

Rủi ro cũ:

```text
Tạo node Quiz thành công
→ cấu hình timer hoặc insert ItemBank lỗi
→ DB báo failed nhưng node rác vẫn tồn tại trên Studio
```

Luồng mới:

```text
create_quiz_node
→ upsert timer
→ insert ItemBank
→ nếu lỗi: delete_quiz_node best-effort
→ ghi rollback result/error/manual_cleanup_required
→ worker đánh dấu failed, không báo success giả
```

Nếu rollback remote thất bại, instance có trạng thái `rollback_manual_required` và metadata đủ để vận hành dọn thủ công.

## 3. Chốt Release và publish/public bộ đề

### 3.1. Snapshot Release bất biến

Publish chỉ đọc `BankReleaseQuestion` đã snapshot khi chốt Release, không tự lấy thêm câu approved hiện tại.

Trước publish kiểm tra:

- Snapshot có dữ liệu.
- Không trùng question ID.
- Mọi question còn tồn tại.
- Trạng thái vẫn là approved/published.
- Không retired/duplicate.
- SHA-256 membership khớp metadata lúc chốt.

Nếu snapshot thay đổi hoặc câu không còn hợp lệ, publish bị chặn và yêu cầu tạo Release mới. Không âm thầm thay membership.

### 3.2. Idempotency và verify component

Với component ID đã lưu:

- Gọi verify trước.
- Nếu Open edX xác nhận tồn tại: reuse, không import trùng.
- Nếu verify xác nhận không tồn tại: import lại.
- Nếu endpoint verify không khả dụng: giữ component ID và trả cảnh báo cần kiểm tra; không import trùng mù quáng.

### 3.3. Atomic database state và compensating rollback

- Chỉ cập nhật question/release thành published sau khi toàn bộ snapshot có kết quả component.
- Không cho Library key thay đổi giữa chừng sau khi đã import một phần.
- Khi lỗi giữa batch, xóa best-effort các component vừa import trong request hiện tại.
- Ghi `manual_cleanup_required` nếu có component không rollback được.
- Worker bắt buộc `result.ok == true`; không còn job completed với payload `ok=false`.

## 4. Đồng bộ AP

### 4.1. Request bất biến

Frontend gửi rõ:

- kỳ;
- hệ;
- danh sách cơ sở;
- phạm vi;
- danh sách môn nếu scope theo môn;
- dry-run.

Backend normalize, sort, deduplicate và tạo SHA-256 fingerprint. Worker đọc lại payload từ DB, normalize lại và so fingerprint trước khi gọi AP.

Nếu request_json bị sửa sau enqueue:

```text
AP_SYNC_REQUEST_INTEGRITY_FAILED
```

Job bị fail và không gọi AP.

### 4.2. Chống job trùng và race condition

- Request giống job đang chạy: reuse job hiện tại.
- Request khác phạm vi trong cùng kỳ/hệ: trả 409 để tránh hai import giao nhau.
- PostgreSQL dùng `pg_advisory_xact_lock` theo `term + branch` để hai thao tác đồng thời không cùng nhìn thấy “chưa có job” rồi enqueue trùng.
- Job cũ từ build trước chưa có fingerprint vẫn chạy được trong rolling deployment; job mới bắt buộc target rõ ràng.

### 4.3. Worker không báo thành công giả

Worker lưu error envelope gồm:

- semantic code;
- message;
- retryable;
- progress cuối.

Lỗi Redis/Celery khi enqueue trả 503 và run được đánh dấu failed thay vì để trạng thái queued vĩnh viễn.

## 5. Cập nhật cơ sở

Frontend sửa cơ sở dùng đúng:

```text
PATCH /api/academic/campuses/{campus_id}
```

Backend:

- 404 khi không tồn tại.
- 409 khi mã/hệ trùng.
- Cho sửa tên, trạng thái, thứ tự.
- Chặn đổi mã/hệ nếu đang có lớp hoặc role CAMPUS liên kết.
- Ghi audit với identity trước/sau.

### RBAC được đóng lại

`CAMPUS_OWNER` chỉ quản lý lớp trong scope campus, không được sửa danh mục campus toàn cục hoặc chạy import AP xuyên cơ sở.

Các endpoint mutation campus và AP job chỉ cho System Admin/`manage_settings`. Frontend menu, route gate và button dùng cùng permission. Route trực tiếp của user không có quyền không còn tự gọi API admin trong `useEffect`.

## 6. Course sync dự phòng

`/courses/sync` và clean-resync:

- Normalize trước khi kiểm tra course scope.
- Ghi sync state bằng canonical Course ID.
- Clean-resync xóa cả canonical và legacy slash form.
- Audit giữ cả canonical và giá trị người dùng đã gửi.

Điều này bảo đảm fallback cho Quiz map tìm được dữ liệu sync cũ đúng course.

## 7. Frontend error/UX contract

- Course ID normalize trên blur và trước API call.
- Hiển thị nguồn cây course: direct, cached hoặc unavailable.
- Không nuốt lỗi lịch sử Quiz.
- Không hiển thị nhiều lỗi Section suy luận sai khi connector lỗi toàn cục.
- Publish Release hiển thị số component verify/reuse và cảnh báo verification.
- AP/Cơ sở không render action hoặc gọi API admin khi thiếu quyền.

## 8. Verification đã chạy

### PASS

- Python compileall backend và connector plugin.
- Ruff undefined-name check.
- Focused cross-layer + frontend/backend contract: `18 passed`.
- TypeScript strict check.
- ESLint zero warning.
- Next.js production build: `30/30` routes.

### Legacy mixed pack

Một pack lịch sử cho các release cũ cho kết quả:

```text
24 passed, 2 skipped, 14 failed
```

14 lỗi không phải runtime failure mới của Batch 16. Chúng khóa literal của các baseline cũ, ví dụ:

- bắt version `.64.13`/`.64.15` trong source hiện tại;
- khẳng định chưa có migration `0053` dù baseline canonical đã có `0053`;
- yêu cầu wording/UI đã được người dùng chủ động loại bỏ;
- tìm logic trong file monolith cũ sau khi workflow đã được tách module.

Đây là test debt cần gom lại thành test theo capability/behavior thay vì test literal lịch sử. Không sửa source hiện tại để làm thỏa các assertion lỗi thời.

## 9. Giới hạn xác minh

Môi trường thực thi không truy cập được UAT nội bộ có SSO, Redis, PostgreSQL, AP và Open edX thật. Vì vậy chưa thể khẳng định connector credential, dữ liệu course thật hoặc plugin đã deploy đúng trên UAT.

Sau deploy cần smoke test thực tế tối thiểu:

1. Cập nhật tên một cơ sở rồi tải lại.
2. Enqueue AP dry-run và xác nhận worker nhận đúng fingerprint.
3. Preview Course ID `course-v1:FPT+COM1071+SU26/` và kiểm tra request sang Open edX đã bỏ `/`.
4. Tắt direct Course Blocks tạm thời hoặc mô phỏng lỗi để xác nhận fallback CourseSyncState.
5. Tạo một Quiz UAT, cố tình làm lỗi ItemBank để xác nhận node được rollback.
6. Publish một Release nhỏ, chạy lại publish để xác nhận không tạo component trùng.

## 10. Database boundary

- Không có migration mới.
- Không reset/xóa dữ liệu.
- Không sửa tay `alembic_version`.
- Alembic head giữ nguyên `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
