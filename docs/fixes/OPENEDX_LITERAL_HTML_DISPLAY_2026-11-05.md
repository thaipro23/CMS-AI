# Câu hỏi HTML/CSS bị mất chữ khi publish lên CMS

## Nguyên nhân và phạm vi

File WEB3023 người dùng cung cấp có 8 sheet, 292 câu. Quiz 01, câu 32 bắt đầu
ở dòng 119: các lựa chọn là `<time>`, `<main>`, `<details>`, `<section>`, đáp án B.
Ảnh Studio cho thấy lựa chọn trống và widget Details thay vì chữ `<details>`.

Importer giữ nguyên các chuỗi này. Lỗi ở ranh giới OLX XML → HTML:
`openedx_exporter._safe_text` chỉ escape XML; sau khi XML được parse, CAPA
`stringify_children` ghép `.text` đầu phần tử trực tiếp vào HTML. `<details>`
đã được XML giải mã trở thành một phần tử HTML thật.

Đối chiếu source Open edX `release/ulmo`:
- [stringify_children](https://github.com/openedx/openedx-platform/blob/release/ulmo/xmodule/stringify.py).
- [ChoiceGroup.extract_choices](https://github.com/openedx/openedx-platform/blob/release/ulmo/xmodule/capa/inputtypes.py).
- [CAPA label extraction](https://github.com/openedx/openedx-platform/blob/release/ulmo/xmodule/capa/capa_problem.py).
- [Dropdown template](https://github.com/openedx/openedx-platform/blob/release/ulmo/xmodule/capa/templates/optioninput.html)
  đã escape text/value riêng; không áp dụng cách bọc lựa chọn radio vào dropdown.

## Hợp đồng xuất nội dung

- `_display_text` bọc text có `<`, `>` hoặc `&` bằng span và escape nội dung XML.
  CAPA serialize phần tử con, giữ entities đến lượt parse HTML của trình duyệt.
  Ví dụ: `<choice correct="true"><span style="white-space: pre-wrap">&lt;main&gt;</span></choice>`.
- Áp dụng cho prompt, lựa chọn single/multi, feedback, hint, solution, nguồn và
  đoạn chữ quanh dropdown. `white-space: pre-wrap` giữ xuống dòng/indent của mã.
- `_safe_text` vẫn dùng cho thuộc tính XML, đáp án text/numeric, option dropdown,
  URL/alt ảnh. Không double-escape toàn bộ OLX hoặc thay giá trị dùng chấm điểm.
- Tiêu đề câu manual/import giữ nguyên ký tự mã HTML; không xóa các đoạn `<...>`.
- Không biến đổi dữ liệu câu hỏi trong DB hoặc file Excel. Câu nhập mới và các
  câu cũ được tái xuất đều dùng cùng exporter. Không cần migration/frontend/CMS-FPT
  rebuild; backend và generation/publish workers cần cùng image đã sửa.

## Kiểm chứng local

- Trước sửa: 10 regression fail, một kiểm tra bảo toàn ảnh pass.
- Sau sửa: 45 test exporter/import pass, gồm 13 regression mới về literal HTML,
  entities, prompt, lựa chọn, hint, source, multiline, grading values và media.
- Đọc toàn bộ workbook bằng importer thật: 254 câu vượt validation hiện tại,
  cả 254 xuất thành XML hợp lệ; đối chiếu 884 choice labels qua XML → HTML đều
  giữ nguyên text. Có 36 câu hợp lệ chứa ký tự HTML/entity cần bảo toàn.
- 38 câu nguồn chưa phù hợp contract import hiện tại, có 73 thông báo:
  INVALID_TYPE 34, INVALID_QUESTION 36, BLANK_ANSWER_COUNT_MISMATCH 2,
  INVALID_OPTION_LABEL 1. Không tự suy diễn TYPE/correct key hay bỏ validation
  để làm các câu này hợp lệ. Đây là vấn đề riêng với lỗi hiển thị câu 32.
- Mô hình render dùng lxml theo đúng thuật toán stringify của CAPA Ulmo. Không
  có runtime Open edX production trong workspace. Thử Playwright bị chặn vì
  thiếu binary Chromium; chưa xác minh giao diện trên Ulmo đang chạy.
- Không đưa toàn bộ file/ngân hàng câu hỏi người dùng vào repository.
- Full backend: 1.363 passed, 16 skipped, 312 failed; từng tên lỗi trùng fresh
  baseline trước sửa (1.350 passed, 16 skipped, 312 failed), không có lỗi mới.
  Bộ test toàn dự án không xanh. CI unit subset: 462 passed; release contract:
  6 passed/1 deselected. Hai integration smoke PostgreSQL/Redis không đạt vì
  local dùng SQLite không có alembic_version và thiếu REDIS_URL; 14 integration
  khác skipped. Không coi lần chạy script local này là CI tích hợp đã pass.
- Ruff F401/F821/E9 của exporter/test mới và git diff --check đạt. 12 test
  script repo_index đạt. Regression mới được thêm vào ci-backend-tests.sh.
- Review độc lập không phát hiện blocker trong exporter; xác nhận yêu cầu sync
  course copy riêng và giới hạn của kiểm thử render local.

## Cập nhật các câu đã publish

Redeploy không tự đổi OLX đã lưu trong CMS. Sau deploy:

1. Xác định đúng Release WEB3023 đang bị ảnh hưởng và Library key hiện tại. Giữ
   nguyên question IDs, Library key, tên bài và học kỳ trong lần sửa hiển thị.
2. Người có quyền publish gửi job bằng endpoint hiện có:

   ```http
   POST /api/question-bank-v2/releases/<release_id>/publish-openedx-job
   Content-Type: application/json

   {"force_reimport": true}
   ```

   Dùng phiên/token có quyền của Dash hiện tại. Theo dõi operation job đến khi
   worker xác minh CMS thành công; request trả job queued chưa phải đã publish.
   Nút/luồng publish thông thường có thể bỏ qua component đã tồn tại, nên cần
   `force_reimport` để thực sự xuất lại OLX bằng exporter đã sửa.
3. Với cùng Library key/question ID, connector dùng block ID định trước từ
   question ID, cập nhật OLX của component có sẵn rồi publish bằng API core.
   Nếu key bị đổi hoặc cần nâng key theo term, dừng để kiểm tra mapping trước;
   không mặc định coi đây là sửa tại chỗ bảo toàn usage key.
4. Nếu course đã copy nội dung từ Library vào Problem Bank/itembank, cập nhật
   bản sao bằng luồng core `sync_library_content`/cập nhật từ Library trong Studio.
   Publish Release không tự gọi bước này. Không xóa Quiz, tạo lại câu, reset
   phiên làm bài hoặc reset điểm để sửa cách hiển thị.
5. Kiểm tra Studio và LMS: thấy đủ bốn chuỗi `<time>`, `<main>`, `<details>`,
   `<section>`; không còn widget Details tự sinh. Đối chiếu câu đáp án B và
   thử dropdown/ảnh trên một bài kiểm tra phù hợp trước khi mở rộng cập nhật.

Trạng thái production: chưa deploy và chưa gửi job sửa nội dung trong phiên này.

## Chạy lại 8 Bài WEB3023 bằng K8s, không qua bước enqueue

Scope được người vận hành chỉ định: subject offering
`f5604c81-3f72-4fa5-8fc0-5dcefd5a26e0` (WEB3023_SU26). Không suy ra phạm vi
FA26 từ course đích; không tự chọn một offering khác chỉ vì cùng mã môn.

Runtime phải chứa cả bản sửa exporter và bản sửa rollback trong changeset này.
Phát hiện thêm: rollback cũ xóa mọi component trong `imported_now`, kể cả câu
có sẵn vừa được cập nhật bởi force reimport. Đã đổi: force reimport không xóa
component khi lỗi; first publish chỉ xóa nếu connector trả `created is True`.
Khi lỗi, OLX của một số câu có thể đã cập nhật; giữ component, ghi failed và
`retained_component_ids`, không giả vờ đã khôi phục nội dung cũ.

Script trong image backend: `/app/republish_web3023_releases.py`.

```bash
# Chỉ đọc kế hoạch; chưa tạo job, chưa gọi CMS.
kubectl -n openedx exec deployment/ai-server-worker -- \
  python -u /app/republish_web3023_releases.py

# Người dùng đã yêu cầu chạy cả 8 Bài. Giữ terminal mở để nhận kết quả từng job.
set -o pipefail
kubectl -n openedx exec deployment/ai-server-worker -- \
  python -u /app/republish_web3023_releases.py --execute \
  | tee web3023-republish.log
```

- Chạy tuần tự `bank_release_publish_task.run(job_id)` bên trong worker image,
  dùng cùng service, progress, durable job và audit; không gọi Celery enqueue.
  Đây không phải sửa lỗi 503 enqueue. Kết nối DB/CMS vẫn phải hoạt động.
- Khóa advisory PostgreSQL chống chạy trùng script; khóa Release và kiểm tra
  lại job queued/running trước mỗi thao tác. Không đổi trạng thái job cũ để vượt khóa.
- Preflight bắt buộc đúng WEB3023, đúng offering, đủ Bài 1–8, Release đã từng
  published, Library key hiện tại bằng quy tắc hiện hành, đủ snapshot/ID câu.
  ID phải là Library V2 canonical từ UUID question ID; không tự migrate ID legacy.
- Chụp toàn bộ mapping vào `repair_expectations`, kiểm tra lại kế hoạch trước
  từng job. Worker/service kiểm tra lại mapping và quy tắc key ngay khi chạy,
  không cho đổi key vì đổi title/term, không chấp nhận key mới từ connector kể
  cả retry, verify component hiện có trước update và từ chối ID trả về khác.
  Script dừng nếu scope/mapping không khớp; không tạo Library/Quiz thay thế.
- Mỗi job có provenance `k8s-operator:web3023-html-repair`. Lỗi dừng batch;
  không tạo sẵn 8 job queued không có broker. Chỉ in DONE 8/8 khi cả 8 job có
  status completed và kết quả ok. Không khẳng định course copy đã sync.
- Sau đó cập nhật bản sao Library trong Studio/course như mục trên. Không
  reset phiên làm bài, student answers, điểm hoặc tạo lại Quiz.

Kiểm chứng source: 64 test exporter/import/rollback/scope pass. Test rollback
trước sửa: 6 failed/2 passed; sau sửa các trường hợp force/existing/unknown
đều giữ component, first publish created thật vẫn được cleanup. Chưa chạy
script với PostgreSQL/CMS thật hoặc K8s: workspace không có kubectl/kết nối
cluster. CLI --help, lint các file mới/workflow/worker và kiểm tra cú pháp đạt;
adapter giữ nguyên 18 F401 so với baseline, không sửa ngoài scope. Fresh full
baseline: 312 failed/1.363 passed/16 skipped; sau sửa: 312 failed/1.382 passed/
16 skipped, cùng 312 tên lỗi. CI subset 481 passed; release contract 6 passed/
1 deselected; integration smoke vẫn 2 failed/14 skipped do thiếu PostgreSQL và
REDIS_URL local. Review độc lập không còn blocker. Không coi đó là production acceptance.
