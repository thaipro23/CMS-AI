# API kết quả phân tích học tập cho AP — v1

AP **backend** gọi Dash qua HTTPS. Dữ liệu lấy từ snapshot phân tích đã tính trong
Dash; GET không quét tracking log, gọi CMS/AP, cập nhật điểm hay tạo job. API này
không tự thay đổi lịch phân tích hiện có. Không cần migration hoặc đổi Redis.

## Một key chung cho AP

Build/deploy backend mới rồi cấu hình Secret môi trường `AP_ANALYTICS_CONFIG_JSON`
trên **API deployment**. Một key duy nhất dùng chung cho AP đọc Poly/PTCD; không
cần client ID và không cấp key theo từng hệ. Quyền vẫn giới hạn theo các cặp
branch/campus khai báo ở phía Dash. Mặc định chưa cấu hình: endpoint trả 503.

Tạo key một lần trong môi trường quản lý secret an toàn, không gửi key qua chat,
commit, URL, frontend hoặc access log:

```python
import hashlib
import secrets
key = secrets.token_urlsafe(32)
print('AP backend key:', key)
print('Dash key_sha256:', hashlib.sha256(key.encode()).hexdigest())
```

AP lưu key gốc. Dash lưu digest SHA-256 và toàn bộ scope được cấp trong cùng JSON:

```json
{
  "key_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_CHARACTERS",
  "scopes": [
    {"branch": "poly", "campuses": ["HN", "DN"]},
    {"branch": "ptcd", "campuses": ["HN", "DN"]}
  ]
}
```

Dùng **đúng mã đang lưu ở AcademicClass.campus**, không dùng nhãn hiển thị.
Không có wildcard. Branch chỉ nhận poly/ptcd. Quyền giữ từng cặp branch/campus:
chỉ cấp poly/HN và ptcd/DN thì không được đọc poly/DN. JSON sai/rỗng, digest sai
hoặc scope rỗng làm integration fail closed. Không fallback từ config mới bị
lỗi sang config cũ, session hay credential `ACADEMIC_AP_API_KEY` outbound.

Để chuyển tiếp image trước: `AP_ANALYTICS_CLIENTS_JSON` còn được chấp nhận nếu
chứa **đúng một** client hợp lệ; key đó được dùng chung mà không cần header ID.
Nhiều client/key cũ trả 503, cần gộp thành config chung rõ ràng. Khi config mới
có giá trị, config mới là nguồn duy nhất. `X-AP-Client-Id` cũ được bỏ qua.

Quay vòng key bằng cách cập nhật digest trong Secret Dash và key AP ở cùng đợt
rollout, xác minh rồi loại secret cũ. Không giữ nhiều key hoạt động. Việc chuyển
key có thể tạo cửa sổ 401 ngắn khi hai bên chưa cùng phiên bản. AP phải phân quyền
người xem trước khi gọi; key không được đưa xuống trình duyệt hoặc dùng thay cho
quyền một giáo viên/sinh viên. Cần bảo vệ/thu hồi key ở mọi bên cùng sử dụng.

## Request

Headers cho cả hai endpoint:

```http
X-AP-API-Key: <secret-from-AP-backend>
```

```http
GET /api/integrations/ap/v1/classes/{ap_class_id}/learning-results?branch=poly&campus=HN&ap_term_id={AP_TERM_ID}&subject_code=WEB3023&limit=100&offset=0
GET /api/integrations/ap/v1/classes/{ap_class_id}/students/{student_code}/learning-results?branch=poly&campus=HN&ap_term_id={AP_TERM_ID}&subject_code=WEB3023
```

| Input | Quy tắc |
|---|---|
| `ap_class_id` | ID lớp AP trong `AcademicClass.ap_class_id`, **khác Dash class UUID** |
| `ap_term_id` | ID kỳ AP, không phải Dash term UUID; bắt buộc |
| `branch`, `campus`, `subject_code` | Bắt buộc, khớp chính xác dữ liệu lớp/kỳ/môn |
| `ap_block_id` | Tùy chọn, dùng ID block AP để phân biệt khi lớp trùng trong nhiều block |
| `student_code` | RollNumber/mã sinh viên đúng case, phải có trong roster active của lớp; không thay bằng email/username |
| `limit`, `offset` | Chỉ endpoint lớp; mặc định 100/0, limit 1–200, offset ≥0 |

Không nhận `course_id` từ caller làm nguồn chọn kết quả: mapping lớp hiện hành
của Dash quyết định course. Class override được ưu tiên như Student/Teacher Ops.
Mapping đổi sẽ không trả snapshot của course cũ. Chỉ snapshot đúng class/course
và sinh viên còn active trong roster được dùng; snapshot người ngoài bị loại.

## Response

Cả hai response có `schema_version: "1"`, `read_only: true`, `context` và
`disclaimer`. `context` gồm AP class/term/block ID, branch, campus, subject_code
và course_id đã map. Không trả email, raw answers, evidence, danh sách bạn học
so sánh, internal doctor hay permission grants.

Endpoint lớp trả `summary`, `total`, `limit`, `offset`, `next_offset`, `items`.
`next_offset: null` khi hết trang. Thứ tự ổn định theo student_code rồi Dash
student ID; roster thay đổi trong lúc phân trang có thể làm kết quả dịch chuyển.
Summary tính **toàn roster**, không chỉ trang hiện tại:

```json
{
  "roster_count": 40,
  "snapshot_count": 35,
  "missing_snapshot_count": 5,
  "stale_snapshot_count": 2,
  "data_status": "partial",
  "classification_counts": {"NORMAL": 20, "POSSIBLE_IDLE": 15}
}
```

`data_status` là `not_calculated` nếu chưa có snapshot, `partial` khi thiếu/cũ,
`ready` khi toàn roster có snapshot còn mới và đúng phiên bản quy tắc. Roster rỗng trả total 0 và
not_calculated. `classification_counts` chỉ đếm snapshot có thật (cả snapshot cũ).

Mỗi `items[]` có cấu trúc như `result` của endpoint sinh viên:

```json
{
  "student_code": "PH12345",
  "full_name": "Nguyễn Văn A",
  "status": "missing",
  "classification": null,
  "display_label": "Chưa có kết quả phân tích",
  "confidence_score": null,
  "reason_codes": ["MISSING_BEHAVIOR_SNAPSHOT"],
  "human_readable_summary": "",
  "recommended_action": "INSUFFICIENT_DATA_RECHECK_LATER",
  "data_quality": "MISSING",
  "calculated_at": null,
  "last_activity_at": null,
  "snapshot_stale": true,
  "snapshot_recompute_required": false
}
```

| Field/trạng thái | Cách AP hiển thị |
|---|---|
| `status: missing` | Chưa có kết quả; tuyệt đối không đổi null thành điểm 0 hoặc NORMAL |
| `status: stale` | Kết quả lịch sử, cần cập nhật; giữ classification cũ và hiện cảnh báo cũ |
| `status: ready` | Snapshot còn mới, **không có nghĩa chất lượng dữ liệu tốt hoặc đã học đủ** |
| `data_quality`, `confidence_score` | Hiển thị cùng nhận định; giá trị confidence 0 vẫn hợp lệ |
| `classification`, `display_label` | Dùng nhãn đã lưu; mã có thể gồm NORMAL, LIKELY_REAL_LEARNING, POSSIBLE_IDLE, POSSIBLE_ANOMALY, POSSIBLE_CHEATING, INSUFFICIENT_DATA |
| `reason_codes`, `human_readable_summary`, `recommended_action` | Lý do và hướng xử lý từ kết quả tính sẵn; render như text, không HTML |
| `calculated_at`, `last_activity_at` | ISO-8601 UTC có timezone; null nghĩa chưa biết |
| `snapshot_stale` | Quá tuổi snapshot hoặc được tính theo bộ quy tắc cũ |
| `snapshot_recompute_required` | True khi cần tính lại do quy tắc đánh giá thay đổi; giữ kết quả lịch sử, GET không tự ghi/reclassify |
| `student_code: null` | Roster chưa có RollNumber; AP cần đối soát dữ liệu, không suy từ username/email |

Đây là tín hiệu từ log, không phải điểm học tập, kết luận gian lận hoặc bằng chứng
sử dụng AI. AP cần hiển thị disclaimer và để giáo viên/quản lý xác minh.
Không biến GET thành thao tác cập nhật/phân tích đồng bộ. Responses thành công
có `Cache-Control: no-store`; AP không bật CDN/shared cache cho dữ liệu này.

## Mã lỗi và nghiệm thu

| HTTP | Nghĩa |
|---|---|
| 401 | Thiếu/sai key; không dùng Dash login để thay thế |
| 403 | Client không được đọc cặp branch/campus yêu cầu |
| 404 | Lớp không tồn tại/không active trong context hoặc sinh viên không thuộc roster active |
| 409 | `AP_CLASS_AMBIGUOUS`, `AP_STUDENT_AMBIGUOUS`, `COURSE_MAPPING_MISSING` hoặc `ANALYTICS_IDENTITY_AMBIGUOUS`; đối soát identity/mapping, không tự chọn bản ghi đầu |
| 422 | Thiếu query bắt buộc hoặc phân trang/branch sai |
| 503 | Integration chưa cấu hình hoặc cấu hình sai; không retry vô hạn |

Trước khi đưa AP dùng thật: xác nhận AP class/term/block IDs, exact campus và
student_code trên một lớp mỗi scope; thử key sai và cơ sở ngoài quyền; đối chiếu
kết quả với Dash; thử thiếu/cũ/mapping đổi; đo SQL latency và query plan trên
PostgreSQL với roster production. Không có migration; build/deploy và cấp Secret
là bước vận hành bắt buộc. Local SQLite test không chứng minh latency production.
