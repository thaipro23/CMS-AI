# Frontend ↔ Backend API Contract Fix — Batch 9

## Phạm vi

Batch này tiếp tục trực tiếp từ baseline `.64.16.5.7.2.3` cộng các batch giao diện trước đó. Mục tiêu là xử lý nhóm lỗi HTTP 400 không đúng bản chất và kiểm tra luồng thực từ frontend tới backend, thay vì xác nhận frontend/backend riêng lẻ.

Không thay đổi route, API nghiệp vụ, RBAC, database schema, Alembic hoặc Open edX semantics.

## Nguyên nhân gốc đã xác định

### 1. JSON request không luôn có Content-Type

Toàn bộ request frontend đi qua `frontend/lib/api.ts`, nhưng nhiều lời gọi dùng `JSON.stringify(...)` cùng `authHeaders()` không có `Content-Type: application/json`. FastAPI có thể không parse body đúng và trả 400/422 dù payload nhìn đúng trong code frontend.

### 2. Backend biến nhiều lỗi khác nhau thành một lỗi 400

Nhiều route dùng `except Exception` rồi trả `BANK_OPERATION_FAILED` với status 400. Hậu quả:

- bản ghi không tồn tại cũng thành 400 thay vì 404;
- dữ liệu trùng hoặc entity bị khóa cũng thành 400 thay vì 409;
- lỗi connector/timeout hoặc lỗi code backend cũng thành 400 và đổ lỗi cho request frontend;
- frontend chỉ thấy thông báo chung, không biết cần sửa dữ liệu hay báo quản trị.

### 3. Frontend làm mất error code và validation details

`ApiRequestError.code` trước đây luôn là `HTTP_400`, `HTTP_422`... dù backend đã gửi semantic code. Chi tiết Pydantic validation không được hiển thị theo field.

### 4. Unexpected backend error không bảo đảm JSON envelope

Lỗi chưa được route bắt có thể trả plain text/HTML 500. Frontend sau đó báo `INVALID_API_RESPONSE`, làm mất request ID và nguyên nhân phân loại.

### 5. Hierarchy create chờ DB constraint mới phát hiện lỗi

Tạo Bộ môn, Môn học và Bài chưa kiểm tra đầy đủ parent/duplicate trước commit. Khi DB phát sinh `IntegrityError`, session có thể ở trạng thái failed; thao tác audit sau đó có nguy cơ che lỗi gốc bằng `PendingRollbackError`.

## Sửa frontend

### `frontend/lib/api.ts`

- Tự động thêm `Content-Type: application/json` khi body là chuỗi JSON.
- Không can thiệp `FormData`, `Blob`, `URLSearchParams` hoặc binary download.
- Giữ nguyên header caller đã chỉ định.
- `ApiRequestError` giữ thêm `details`.
- Đọc đúng các envelope:
  - `{ error: { code, message, details, request_id } }`
  - `{ detail: { code, message, details } }`
  - response legacy có `detail` dạng string.
- Giữ semantic code backend, ví dụ:
  - `BANK_OPERATION_CONFLICT`
  - `BANK_OPERATION_NOT_FOUND`
  - `VALIDATION_ERROR`
  - `INTERNAL_SERVER_ERROR`
- Chuyển Pydantic validation details thành thông báo theo field.

### `frontend/components/ui/ActionMessage.tsx`

Không còn rút gọn mọi lỗi validation thành một câu chung khi backend đã trả chi tiết cụ thể.

## Sửa backend

### Global error contract

`backend/app/core/errors.py` phân loại lỗi theo semantics:

| Loại lỗi | HTTP |
|---|---:|
| Request/Pydantic validation | 422 |
| Không tìm thấy entity/tệp | 404 |
| Dữ liệu trùng, entity bị khóa, không thể xóa do liên kết | 409 |
| Không có quyền | 403 |
| Timeout | 504 |
| requests/httpx upstream error | 502 |
| Lỗi domain còn lại | status nghiệp vụ đã khai báo, thường 400 |
| Lỗi backend không dự kiến | 500 |

`HTTPException` có sẵn được giữ nguyên thay vì bị bọc lại thành 400.

Thêm global `Exception` handler để mọi lỗi 500 vẫn trả cùng JSON envelope và `X-Request-ID`, không trả plain text cho frontend.

### Loại bỏ broad-exception → direct 400

Đã sửa các vùng có `except Exception` rồi trả trực tiếp HTTP 400 tại:

- Academic course/class mapping;
- AP JSON import;
- course file extraction;
- publish family-bank preview;
- Bank material preflight;
- Bank version diff preview/create.

Lỗi domain hợp lệ vẫn có thể là 400; lỗi conflict/not-found/system/upstream được trả đúng status.

### Hierarchy validation

- Bộ môn: normalize mã, bắt tên/mã rỗng, kiểm tra mã trùng trước commit.
- Môn học: kiểm tra Bộ môn tồn tại, normalize dữ liệu, kiểm tra mã trùng trong Bộ môn.
- Bài: kiểm tra Môn/Phiên bản môn, title và chapter number trùng.
- Audit service tự rollback session failed trước khi ghi failure audit.

## Audit toàn bộ API frontend/backend

Kết quả từ OpenAPI và TypeScript AST:

- Backend: 248 paths, 282 method/path operations.
- Frontend: 224 lời gọi `apiFetch`.
- 221 static calls được đối chiếu tự động.
- 2 lời gọi generic pagination helper được resolve qua callback.
- 1 dynamic question transition được mở rộng thành approve/reject/publish.
- Không thiếu method/path.
- Không có endpoint backend bắt buộc request body nhưng frontend không gửi body.
- 76 lời gọi frontend có body đi qua JSON/header contract dùng chung.

Chi tiết: `FRONTEND_BACKEND_API_CONTRACT_AUDIT_BATCH_9.json`.

## HTTP end-to-end thực tế

Đã chạy luồng bằng chính code `frontend/lib/api.ts` đã compile, gọi qua HTTP tới Uvicorn/FastAPI và database SQLite tạm:

```text
Frontend createDepartment/createSubject/createSubjectChapter
→ apiFetch tự gắn JSON Content-Type và X-Request-ID
→ HTTP
→ FastAPI validation/RBAC demo
→ SQLAlchemy commit
→ JSON response
→ frontend parseResponse
```

Kết quả:

- Tạo Bộ môn: 200.
- Tạo Môn học: 200.
- Tạo Bài: 200.
- Trùng mã Bộ môn: 409 + `BANK_OPERATION_CONFLICT`.
- Payload rỗng: 422 + `VALIDATION_ERROR` + field details.
- Parent không tồn tại: 404 + `BANK_OPERATION_NOT_FOUND`.

Chi tiết: `FRONTEND_BACKEND_HTTP_E2E_EVIDENCE_BATCH_9.json`.

## Verification đã chạy

- Frontend TypeScript: PASS.
- Frontend ESLint zero warning: PASS.
- Next.js production build: PASS, 30/30 routes.
- Backend compileall: PASS.
- Ruff F821: PASS.
- Targeted frontend/backend contract tests: 9/9 PASS.
- OpenAPI ↔ frontend call audit: PASS.
- Runtime HTTP frontend → backend → DB → frontend: PASS.

## Chưa xác minh

- Chưa deploy batch này lên UAT `ai.cms-test.poly.edu.vn`.
- Chưa chạy với SSO cookie và PostgreSQL UAT thật.
- Chưa kích hoạt các thao tác có side effect ngoài hệ thống như AP/Open edX/OpenAI thật.

Sau deploy cần smoke theo dữ liệu thật và lấy `X-Request-ID` của bất kỳ request còn lỗi để đối chiếu backend log.
