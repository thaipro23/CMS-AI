# v25.9.16.7.2.64.37 — Bulk Review & Legacy Data Hardening

## Mục tiêu

Khắc phục lớp lỗi khiến `POST /api/question-bank-v2/bank-versions/{id}/questions/bulk-review`
có thể trả HTTP 500 khi gặp dữ liệu Question Bank legacy hoặc khi backend nhận traffic trước khi
Alembic migration đã được áp dụng đầy đủ.

Bản sửa không reset database, không xóa question/review/release và không sửa Open edX core.


## Điểm cần kiểm tra đầu tiên trên production hiện tại

Bản Hint gần nhất thêm `Question.pedagogy_json` và migration `0058_v25_9_16_7_2_64_36`.
Nếu backend image mới đã rollout nhưng DB vẫn ở revision cũ, mọi ORM query load `Question` có thể fail ngay với lỗi kiểu
`column ai_questions.pedagogy_json does not exist`; `bulk-review` là một endpoint sẽ chạm đúng query này.
Do chưa có traceback/DB runtime trong gói source, đây là **nguyên nhân có xác suất cao cần xác minh**, không được coi là đã chứng minh chỉ từ HTTP 500.

Bản hardening này buộc `/api/health/ready` kiểm tra cả cột `pedagogy_json` và Alembic head 0059, nên deployment mới sẽ fail readiness thay vì nhận traffic với schema cũ.

## Nguyên nhân ở source đã xác định

### 1. Bulk review dùng cùng một SQLAlchemy Session nhưng không cô lập lỗi từng row

Luồng cũ commit trong `review_bank_question()` cho từng question. Nếu một row gây lỗi DB trong
`flush/commit`, Session chuyển sang failed transaction. Bulk loop vẫn tiếp tục dùng Session đó,
nên một row legacy có thể làm các row kế tiếp và audit cuối request thất bại, cuối cùng thành HTTP 500.

Luồng mới:

- transition review không tự commit;
- mỗi question chạy trong `SAVEPOINT` (`begin_nested()`);
- lỗi một row chỉ rollback savepoint đó;
- successful rows commit một lần ở cuối bulk request;
- DB error ở request boundary được rollback và trả lỗi đã sanitize.

### 2. Legacy status trước đây không được tính là unresolved ở mọi nơi

Một số thống kê/release-readiness chỉ đếm các status chuẩn. Status lạ có thể bị bỏ qua và khiến
chapter/bank version trông như đã review xong.

Luồng mới fail-closed:

- status không thuộc tập chuẩn được tính vào `unknown_status_count`;
- unknown status làm `is_review_done=false`;
- Release readiness fail với check `legacy_question_status`;
- dashboard gợi ý action `repair_legacy_status`.

### 3. K8s readiness trước đây chỉ kiểm tra process health

`/api/health` không xác minh schema DB. Backend có thể Ready trong khi migration mới chưa chạy,
dẫn tới lỗi kiểu missing column/table ở request thật.

Bản sửa thêm:

- `GET /api/health/ready`: kiểm tra `SELECT 1`, Alembic revision `0059_v25_9_16_7_2_64_37` và các table/column cốt lõi;
- readiness probe của backend chuyển sang `/api/health/ready`;
- liveness vẫn dùng `/api/health`.

## Migration 0059

File:

`backend/alembic/versions/0059_v25_9_16_7_2_64_37_question_bank_legacy_hygiene.py`

Migration non-destructive:

- lifecycle đã publish/verified/success → `status=published`;
- `NULL`, blank, `draft`, `needs_review`, `generated`, `edited`, `review` → `pending_review`;
- `error` → `draft_error`;
- NULL defaults của các cờ/counter được chuẩn hóa;
- review-log blank status → `legacy_unknown`;
- search-document status được sync lại từ source question.

Status lạ không nằm trong mapping **không được tự sửa**. Chúng được giữ lại để runtime/report phát hiện,
tránh đoán sai ý nghĩa dữ liệu lịch sử.

## Data health audit

Chạy read-only audit trong backend image:

```bash
python scripts/question-bank-data-health.py
```

Script kiểm tra schema, Alembic revision, phân bố status, unknown legacy status, published lifecycle drift,
review-log blank status và search-document mismatch. Script không ghi database.

## Thứ tự rollout bắt buộc

1. Build/push immutable backend image có code + migration mới.
2. Chạy Alembic migration job đến khi COMPLETE.
3. Chỉ sau đó rollout backend/worker cùng image/tag.
4. Kiểm tra `/api/health/ready` trả HTTP 200 và `schema.ready=true`.
5. Chạy `python scripts/question-bank-data-health.py` và xử lý mọi unknown status còn lại trước khi Release.
6. Retest bulk-review trên bank version thực tế.

Không dùng image tag `latest`, không reset DB/PVC và không sửa tay `alembic_version`.
