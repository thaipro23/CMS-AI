# Import Quiz CMS cũ vào SU26

## Mục tiêu

Tính năng `/import-quiz-cms-old` nhận một hoặc nhiều file Excel câu hỏi từ CMS cũ, kiểm tra toàn bộ dữ liệu trước khi ghi, rồi import theo cấu trúc:

`Bộ môn → Môn → Phiên bản môn SU26 → Bài → Bank Version nháp → Câu hỏi Chờ duyệt`

Tên file phải bắt đầu chính xác bằng mã môn đang active và người dùng có quyền truy cập. Ví dụ `MEC229 - Đồ gá.xlsx` chỉ khớp môn `MEC229`; hệ thống không đoán gần đúng và chặn trường hợp không tìm thấy hoặc khớp nhiều môn.

Mỗi sheet ánh xạ thành một bài. Số bài được lấy từ số ở cuối tên sheet (`Quiz 01`, `Q1`); nếu không có thì dùng thứ tự sheet và phát cảnh báo. Hai sheet cùng ánh xạ một số bài là lỗi chặn.

## Quy ước cột

| Cột nguồn | Ý nghĩa | Giá trị hỗ trợ |
|---|---|---|
| `NO` / `STT` | Bắt đầu một câu hỏi mới | Số/thứ tự câu |
| `QUESTION` / `CÂU HỎI` | Nội dung câu | Có thể chứa `[_____]` và `[ten-anh.png]` |
| `ABC` / `LABEL` | Nhãn lựa chọn | `A` đến `L` |
| `ANSWER` / `ĐÁP ÁN` | Nội dung lựa chọn | 2–12 lựa chọn, không trùng nội dung |
| `CORRECT` / `ĐÁP ÁN ĐÚNG` | Đáp án đúng | `A`, `AC`, `A,C`…; thứ tự có ý nghĩa với TYPE 2 |
| `TYPE` | Loại câu hỏi | `0`, `1`, `2` |
| `NGƯỠNG` | Độ khó | `1`, `2`, `3` |

`TYPE` và `NGƯỠNG` là hai trường độc lập:

| `TYPE` | Loại câu canonical |
|---:|---|
| `0` | Chọn một đáp án đúng (`single_select`) |
| `1` | Chọn nhiều đáp án đúng (`multi_select`) |
| `2` | Chọn và điền vào ô trống (`dropdown_fill`) |

| `NGƯỠNG` | Độ khó canonical |
|---:|---|
| `1` | Dễ (`easy`) |
| `2` | Trung bình (`medium`) |
| `3` | Khó (`hard`) |

Nếu file không có cột `TYPE`, hệ thống suy luận từ `CORRECT`: một ký tự là câu một đáp án, nhiều ký tự là câu nhiều đáp án; câu có `[_____]` là câu chọn/điền ô trống. Nếu không có cả `NGƯỠNG` lẫn cột độ khó tương đương, mặc định là Trung bình.

Với `dropdown_fill`, số ký hiệu `[_____]` phải bằng số nhãn trong `CORRECT`, và thứ tự nhãn là thứ tự đáp án cho từng ô. Ví dụ hai ô với `CORRECT=BA` có đáp án ô 1 là B, ô 2 là A. Canonical JSON lưu `correct_option_ids` theo thứ tự và exporter tạo native Open edX `optionresponse`/`optioninput`.

## Ảnh câu hỏi

- Marker ảnh trong câu hỏi dùng dạng `[QN12.png]`, `[hinh-1.jpg]` hoặc WebP.
- Người dùng có thể tải ảnh trực tiếp hoặc một ZIP chứa ảnh; khớp theo basename Unicode NFC, không phân biệt hoa/thường.
- Ảnh nhúng thực sự trong workbook cũng được đọc theo vị trí neo dòng.
- Chỉ nhận PNG/JPEG/WebP hợp lệ, tối đa 4 MB/ảnh và 4 ảnh/câu.
- Câu thiếu hoặc lỗi ảnh bị chặn riêng. Người dùng phải bổ sung ảnh và preview lại, hoặc xác nhận **Bỏ qua câu lỗi** để loại câu đó khỏi ngân hàng đề.
- Tên ảnh trùng nhưng khác nội dung, ZIP có path traversal hoặc vượt giới hạn giải nén là lỗi cấp file và không thể vượt qua bằng nút Bỏ qua.
- File MEC229 mẫu chỉ chứa 36 tham chiếu tên ảnh, không chứa binary ảnh nhúng; cần cung cấp ảnh/ZIP đi kèm.

## Preview và quy tắc lỗi

Preview có thời hạn 2 giờ và không thay đổi dữ liệu môn học. Lỗi chặn gồm:

- không tìm thấy/khớp mơ hồ mã môn;
- thiếu header hoặc vượt giới hạn file, sheet, câu hỏi, archive;
- TYPE, NGƯỠNG, nhãn/correct key không hợp lệ;
- lựa chọn rỗng/trùng, sai số lượng đáp án đúng;
- số ô trống không khớp thứ tự đáp án;
- thiếu hoặc lỗi ảnh trên từng câu.

Khi preview có lỗi gắn với câu hỏi, giao diện đưa ra hai lựa chọn rõ ràng:

1. **Bổ sung ảnh và kiểm tra lại**: cộng thêm ảnh/ZIP vào danh sách đã chọn và chạy lại preview.
2. **Bỏ qua N câu lỗi**: backend loại chính xác các câu có lỗi, tính lại toàn bộ số câu/loại/độ khó và ghi audit người xác nhận. File Excel gốc vẫn được lưu làm tài liệu đối chiếu.

Nút Bỏ qua không loại lỗi cấp môn, workbook hoặc sheet. Ví dụ `SUBJECT_NOT_FOUND`, thiếu header và trùng số bài vẫn chặn import.

Câu hỏi trùng nội dung trong chính nguồn cũ **không bị loại**. Mỗi dòng vẫn được bảo toàn bằng source identity riêng, gắn cờ `duplicate_in_legacy_source` và bắt buộc người duyệt xử lý.

## Ghi dữ liệu và khả năng retry

Job import khóa môn/chapter trong lúc bảo đảm cấu trúc đích:

1. Dùng lại phiên bản môn có `term=SU26` hoặc mã `{SUBJECT}_SU26`; nếu chưa có thì tạo draft.
2. Dùng lại hoặc tạo bài theo số sheet.
3. Dùng Bank Version mới nhất đang `draft`/`reviewing`; nếu không có thì tạo `vN.0` draft.
4. Tạo một `LearningMaterialVersion` cho mỗi sheet, trỏ tới workbook đã lưu và ghi `uploaded_by`.
5. Tạo câu với `authoring_mode=import`, `source_type=legacy_quiz_excel`, `model_provider=manual`, `created_by=<người import>`, `status=pending_review`.
6. Ghi `QuestionReviewLog` từ `imported` sang `pending_review`, actor là người import.

Retry dùng bộ ba `bank_version_id + source_node_id + source_ref`, không dùng content hash. Vì vậy retry cùng preview không tạo lặp, nhưng các dòng trùng có chủ đích trong file vẫn tồn tại riêng.

## API và phân quyền

| Endpoint | Chức năng |
|---|---|
| `POST /api/question-bank-v2/import-quiz-cms-old/preview` | Multipart `workbooks` và `assets`; phân tích, lưu preview tạm |
| `POST /api/question-bank-v2/import-quiz-cms-old/skip-errors` | JSON `{ "preview_token": "..." }`; loại các câu lỗi sau xác nhận, nhưng giữ nguyên lỗi cấp file/môn/sheet |
| `POST /api/question-bank-v2/import-quiz-cms-old/jobs` | JSON `{ "preview_token": "..." }`; tạo job nền |
| `GET /api/question-bank-v2/operation-jobs/{job_id}` | Theo dõi tiến độ/kết quả |

Người dùng cần quyền legacy `edit_questions`; trước khi enqueue, backend kiểm tra lại `subject.update`, `document.manage` và `question.edit` trên từng môn khớp. Preview chỉ tìm trong các môn active thuộc phạm vi nhìn thấy của người dùng.

## Kết quả phân tích ba file mẫu

| File | Sheet | Câu | Loại câu | Độ khó | Ghi chú |
|---|---:|---:|---|---|---|
| HOS2032 | 11 | 308 | 165 đơn, 61 nhiều, 82 ô trống | 308 Trung bình | Hợp lệ theo cấu trúc |
| MEC129 | 8 | 406 | 350 đơn suy luận, 56 nhiều suy luận | 312 Dễ, 94 Trung bình | 6 nhóm prompt trùng, chỉ cảnh báo |
| MEC229 | 8 | 224 | 171 đơn, 53 nhiều | 224 Trung bình | 36 tham chiếu ảnh; 6 nhóm prompt trùng; 1 câu lỗi đáp án trùng tại `Quiz 01`, dòng Excel 238 |

## Triển khai

Không có thay đổi schema cơ sở dữ liệu, vì tính năng dùng các bảng và trường audit hiện có. Cần deploy đồng thời backend API, worker Celery và frontend. Worker `bank_legacy_quiz_import_task` chạy trên queue `generation`; object storage phải được cấu hình và worker phải truy cập cùng storage với API.

Kiểm tra tối thiểu trước deploy:

```bash
PYTHONPATH=backend pytest -q backend/app/tests/test_legacy_quiz_cms_old_import.py
ruff check backend/app/services/question_bank/legacy_quiz_import.py backend/app/services/question_content.py backend/app/services/openedx_exporter.py backend/app/api/routes/question_bank_v2.py backend/app/worker.py
cd frontend && npm run typecheck && npm run lint && npm run build
```
