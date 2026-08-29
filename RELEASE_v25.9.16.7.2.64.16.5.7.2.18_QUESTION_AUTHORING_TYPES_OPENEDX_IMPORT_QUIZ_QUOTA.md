# Release v25.9.16.7.2.64.16.5.7.2.18 — Question Authoring Types, Open edX Import & Quiz Type Quota

## Mục tiêu

Mở rộng ACMS từ mô hình câu hỏi A/B/C/D một đáp án thành bộ soạn câu hỏi có schema chuẩn, vẫn tương thích dữ liệu cũ và publish native Open edX mà không sửa Open edX core.

Release này hoàn thiện một vertical slice xuyên suốt:

`PostgreSQL/Alembic → API → service → AI generation → manual editor → media/MinIO → review → release → Open edX connector/static asset → Quiz planner → worker/error boundary → frontend`.

## Loại câu hỏi hỗ trợ

- `single_select`: một đáp án đúng.
- `multi_select`: nhiều đáp án đúng.
- `text_input`: trả lời ngắn, hỗ trợ nhiều accepted answer và chế độ phân biệt hoa/thường.
- `numerical_input`: trả lời số, hỗ trợ tolerance tuyệt đối hoặc phần trăm.

Tên ACMS được tách khỏi tên XML Open edX để tránh nhầm `multiplechoiceresponse` với câu chọn nhiều.

## Canonical Question schema v2

`ai_questions` bổ sung:

- `question_schema_version`;
- `authoring_mode` (`ai`, `manual`, `import`);
- `created_by`;
- `question_content_json`.

Các cột legacy `option_a..option_d` và `correct_answer` vẫn được giữ làm compatibility mirror để dữ liệu và code cũ tiếp tục hoạt động. Canonical JSON là nguồn sự thật cho câu hỏi mới.

## Manual authoring trên ACMS

Chapter Workspace có:

- `+ Thêm câu hỏi`;
- editor động theo 4 response type;
- add/remove/reorder logical option bằng stable option id;
- phản hồi từng option;
- hint/explanation/learning objective/concept/family/source;
- preview learner-style;
- ảnh câu hỏi;
- câu thủ công luôn bắt đầu `pending_review`, không bypass review workflow.

## Media câu hỏi

Migration `0060` tạo `ai_question_media`.

Contract:

- lưu file qua ObjectStorage/MinIO, không nhét base64 vào PostgreSQL;
- PNG/JPEG/WebP;
- từ chối SVG;
- kiểm MIME bằng nội dung thật;
- SHA-256;
- alt text bắt buộc;
- tối đa 4 MB/ảnh, 4 ảnh/câu, 16 MB media/câu khi publish;
- endpoint đọc media yêu cầu quyền ACMS;
- xóa media DB và best-effort cleanup object storage.

Khi publish, AI Server gửi media sang Open edX connector, connector dùng Content Libraries static asset API rồi thay placeholder trong OLX. Learner OLX không phụ thuộc MinIO presigned URL.

## AI generation Multi-select

ModelGateway có Structured Output contract riêng theo `target_question_type`.

`single_select` yêu cầu `correct_answer` đúng một A/B/C/D.

`multi_select` yêu cầu `correct_answers`:

- 2–3 nhãn đúng;
- unique;
- chỉ A/B/C/D;
- không cho tất cả 4 đáp án cùng đúng.

Model output được validate lần hai trước DB. Option shuffle giữ đúng toàn bộ correct labels và remap pedagogy/misconception theo option text.

Chapter generation cho phép tỷ lệ Single/Multi. Allocator bảo toàn đồng thời tổng số câu, material allocation và EASY/MEDIUM/HARD; không làm tròn độc lập gây sai tổng.

## Open edX import

Parser/import giữ grading semantics cho:

- `multiplechoiceresponse` / `choicegroup` → `single_select`;
- `choiceresponse` / `checkboxgroup` → `multi_select`;
- `stringresponse` → `text_input`;
- `numericalresponse` → `numerical_input`.

`stringresponse type="regexp"` và grading mode chưa hỗ trợ bị fail-closed thay vì âm thầm đổi cách chấm.

API:

- `POST /api/question-bank-v2/bank-versions/{id}/questions/import-openedx/preview`
- `POST /api/question-bank-v2/bank-versions/{id}/questions/import-openedx`

Import tạo `authoring_mode=import`, `status=pending_review`. OLX chứa ảnh được cảnh báo để giáo viên upload lại media vào ACMS; release này không đoán/copy asset URL ngoài phạm vi một cách không an toàn.

## Open edX export

Exporter native:

- `single_select` → `multiplechoiceresponse`;
- `multi_select` → `choiceresponse + checkboxgroup`;
- `text_input` → `stringresponse`;
- `numerical_input` → `numericalresponse`.

Không sửa Open edX core. Thay đổi phía Open edX nằm trong `openedx-connector-plugin`.

## Quiz Blueprint exact type quota

Migration `0061` bổ sung vào `ai_quiz_blueprints`:

- `single_select_count`;
- `multi_select_count`;
- `text_input_count`;
- `numerical_input_count`.

Planner giải constraint đồng thời:

- total questions;
- EASY/MEDIUM/HARD;
- question type quota;
- availability thực tế của Release;
- không trùng question/component giữa ItemBank.

Planner dùng bounded max-flow cho ma trận `difficulty × question type`; impossible matrix fail trước side effect Open edX với thông tin availability.

Blueprint legacy có quota NULL được hiểu theo behavior cũ: toàn bộ là `single_select`.

## Error/exception hardening

Release bổ sung `scripts/error-boundary-contract-check.py` và nối vào UAT/Claude gates.

Blocker được bắt gồm:

- bare `except`;
- Celery broad exception `return` khiến task báo SUCCESS giả;
- raw unexpected exception leak ra HTTP public message.

Worker heavy job persist failure state rồi re-raise để Celery phản ánh đúng trạng thái.

RBAC cũng được harden: `CAMPUS_MANAGER` chỉ còn legacy alias để đọc/revoke assignment cũ, không thể được cấp mới qua single API, batch API, import Excel, UI hoặc direct service call. Dùng `CAMPUS_OWNER` cho assignment mới.

## Migration

Alembic chain:

`0059_v25_9_16_7_2_64_37`
→ `0060_v25_9_16_7_2_64_38`
→ `0061_v25_9_16_7_2_64_39` (head)

Cả 0060/0061 là additive và có downgrade path được smoke-test bằng SQLite. Production vẫn phải chạy migration trên PostgreSQL/UAT trước rollout backend mới.

## Sonar / CI

Jenkins SonarQube Analysis vẫn scan `backend/app,frontend`. Release xử lý các lỗi source contract thuộc phạm vi thay đổi và thêm test/gate static. SonarQube server Quality Gate do DevOps quản lý; sandbox không có Sonar token/server để tuyên bố Quality Gate production PASS.

## Version

Current application version: `25.9.16.7.2.64.16.5.7.2.18`.
