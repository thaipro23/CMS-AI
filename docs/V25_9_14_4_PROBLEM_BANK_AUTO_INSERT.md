# v25.9.14.4 — Problem Bank Auto Insert

## Mục tiêu

Bản này nối tiếp v25.9.14.3. Sau khi AI Server đã tạo được Quiz node/Unit thật trong Open edX Studio, bản v25.9.14.4 thêm bước insert các **Problem Bank / `library_content` block** vào Unit đó theo Family Slot Plan.

Luồng mong muốn:

1. Giáo viên sync course trong `/sync`.
2. Giáo viên tạo/generate/review câu hỏi.
3. Giáo viên tính Family Slot Problem Bank Plan trong `/export`.
4. Giáo viên publish variants trong plan vào Chapter Library.
5. Giáo viên chọn node cha CMS và bấm **Tạo Quiz + Problem Bank**.
6. AI Server gọi CMS connector tạo Quiz Unit thật.
7. AI Server gọi CMS connector insert mỗi slot thành một `library_content` block trong Unit.

## Nguyên tắc trung thực / không fake success

Bản này không báo thành công giả:

- Nếu `USE_MOCK_OPENEDX=true`, backend chặn insert Problem Bank.
- Nếu plan chứa question chưa publish sang Open edX Library, backend báo lỗi và yêu cầu publish plan trước.
- Nếu một slot có question thuộc nhiều library khác nhau, backend báo lỗi vì một Problem Bank slot chỉ trỏ về một library.
- CMS connector phải tạo được block thật và trả `usage_key` thật.
- Connector đọc lại block sau khi tạo để verify `source_library_id`, `max_count`, `manual`, `shuffle`.
- Connector chỉ đặt `selection_verified=true` khi đọc lại thấy selected children/usage keys chứa đủ component đã yêu cầu.
- Nếu Open edX Ulmo.3 không expose selected component field theo cách mong muốn, API vẫn trả block đã tạo nhưng kèm `manual_component_selection_required=true` và warning. Không coi là “đã random đúng variants” nếu chưa verify được selected components.
- Nếu bật `strict_component_selection=true`, backend sẽ lỗi khi selected components chưa verify được.

## API mới trong AI Server

```http
POST /api/publish/courses/{course_id}/cms-problem-banks/insert
```

Payload:

```json
{
  "unit_node_id": "block-v1:FPT+MUL211+SU26+type@vertical+block@quiz_tu_luyen",
  "plan": {
    "slots": []
  },
  "strict_component_selection": false
}
```

Response rút gọn:

```json
{
  "ok": true,
  "created": true,
  "status": "created_with_manual_selection_required",
  "unit_node_id": "block-v1:...+type@vertical+block@quiz_tu_luyen",
  "slots_requested": 10,
  "slots_inserted": 10,
  "manual_component_selection_required": true,
  "problem_bank_blocks": [
    {
      "usage_key": "block-v1:...+type@library_content+block@...",
      "block_type": "library_content",
      "display_name": "Problem Bank Slot 01 - Vector/Raster",
      "slot_no": 1,
      "library_key": "lib:FPT:MUL211-bai-2",
      "pick_count": 1,
      "selection_verified": false
    }
  ],
  "warnings": []
}
```

## API mới trong CMS connector

```http
POST /api/ai-connector/v1/courses/{course_id}/problem-banks
```

Endpoint này chạy trong Studio/CMS và tạo child block type:

```text
library_content
```

Các field connector cố gắng set:

```text
display_name
source_library_id
source_library_version = null
manual = true
shuffle = true
max_count = pick_count
capa_type = any
children / selected / selected_blocks / source_library_usage_keys
```

Lưu ý: field selected components của `library_content` phụ thuộc implementation của Open edX release. Vì vậy connector verify bằng cách đọc lại block. Nếu không thấy selected children chứa đủ component ID, hệ thống báo cần kiểm tra thủ công trong Studio thay vì báo thành công giả.

## UI mới

Trang `/export` đổi khối tạo Quiz thành:

```text
Tạo Quiz + Problem Bank trên Open edX
```

Có 2 chế độ:

- `Tự insert Problem Bank sau khi tạo Unit`: tạo Quiz Unit xong insert luôn Problem Bank blocks.
- `Strict: lỗi nếu chưa verify selected components`: chỉ dùng khi muốn API fail nếu không chắc selected variants đã gắn đúng.

Có nút:

- `Tạo Quiz + Problem Bank`
- `Chỉ insert Problem Bank`

UI hiển thị bảng các Problem Bank block đã tạo và trạng thái:

- `selected verified`: connector đọc lại thấy selected components đúng.
- `manual check`: block đã tạo nhưng selected components chưa verify được, cần mở Studio kiểm tra/chọn lại.

## Env mới

```env
OPENEDX_PROBLEM_BANK_INSERT_ENDPOINT=/api/ai-connector/v1/courses/{course_id}/problem-banks
```

## Files chính

```text
backend/app/core/config.py
backend/app/modules/openedx_connector/base.py
backend/app/modules/openedx_connector/real.py
backend/app/modules/publisher/service.py
backend/app/api/routes/publish.py
openedx-connector-plugin/openedx_ai_connector/views.py
openedx-connector-plugin/openedx_ai_connector/urls.py
frontend/app/export/page.tsx
frontend/lib/api.ts
frontend/types/index.ts
```

## Cách chạy

Sửa cả AI backend/frontend và CMS plugin nên cần rebuild AI Server và restart CMS/CMS worker.

AI Server:

```bash
docker compose build --no-cache backend worker frontend
docker compose up -d
```

Migration không bắt buộc vì bản này không thêm bảng mới, nhưng có thể chạy theo quy trình chuẩn:

```bash
docker compose exec backend alembic upgrade head
```

CMS plugin:

```bash
tutor local restart cms cms-worker
```

Nếu plugin không mount trực tiếp từ zip, copy các file plugin đã sửa vào repo CMS trước khi restart.

## Cách test thật trên UAT

1. Kiểm tra connector:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

2. Sync course trong `/sync`.

3. Trong `/export`, bấm **AI tính kế hoạch**.

4. Bấm **Đẩy kế hoạch vào Open edX** để publish variants vào Chapter Library. Bước này bắt buộc vì Problem Bank cần component thật trong Library.

5. Chọn node cha `course/chapter/sequential`.

6. Bấm **Tạo Quiz + Problem Bank**.

7. Mở Studio, kiểm tra dưới node đã chọn có Unit Quiz mới và trong Unit có các block `Problem Bank Slot XX`.

8. Nếu UI báo `manual check`, mở từng Problem Bank block trong Studio để xác nhận/chọn lại components. Đây là trạng thái cảnh báo thật, không phải lỗi ẩn.

## Giới hạn còn lại

- Chưa tự publish course outline sau khi tạo blocks.
- Chưa guarantee selected variants nếu Ulmo.3 không lưu selected components vào field connector có thể đọc lại.
- Chưa rollback tự động toàn bộ Problem Bank blocks nếu một slot giữa chừng lỗi.
- Nếu strict mode bật và selected components không verify được, API có thể đã tạo block trong Studio trước khi trả lỗi; cần kiểm tra Studio và logs.
