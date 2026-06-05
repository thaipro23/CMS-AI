# v25.9.14.6 — Native Ulmo ItemBank Auto Insert + Guided Workflow

## Mục tiêu

Bản này thay luồng tạo sai `library_content`/Randomized Content Block bằng native **Problem Bank Beta** của Open edX Ulmo.3:

```text
Unit/vertical
└── itembank (ItemBankBlockWithMixins, max_count=1)
    ├── problem child trong course, upstream=lb:FPT:...:problem:...
    └── problem child trong course, upstream=lb:FPT:...:problem:...
```

Không báo thành công nếu block không phải `itembank`, component chưa được đồng bộ hoặc upstream không đúng.

## Bằng chứng từ môi trường Ulmo.3 thật

Problem Bank tạo thủ công trong Studio có:

```text
CATEGORY: itembank
CLASS: ItemBankBlockWithMixins
max_count: 1
children: block-v1:...+type@problem+block@...
```

Mỗi child problem có:

```text
parent = itembank usage key
upstream = lb:FPT:...:problem:...
upstream_version = published Library version
upstream_display_name = tên component nguồn
```

Studio thêm component vào ItemBank tuần tự bằng payload:

```json
{
  "library_content_key": "lb:FPT:...:problem:...",
  "category": "problem",
  "parent_locator": "block-v1:...+type@itembank+block@..."
}
```

Sau đó CMS gọi `create_xblock(...)`, đặt `created_block.upstream`, rồi gọi `sync_library_content(...)`.

## Luồng triển khai mới

1. Backend chạy Stable Family Hard Duplicate Guard.
2. Tất cả câu trong plan phải đã publish vào đúng Chapter Library.
3. CMS connector tạo `itembank` dưới Unit bằng Studio native `create_xblock`.
4. Đặt `max_count=1`.
5. Với từng Library V2 problem trong slot, connector thêm **tuần tự**:
   - tạo course-local `problem` child;
   - đặt `child.upstream`;
   - gọi `sync_library_content` để đồng bộ OLX, asset và upstream metadata.
6. Đọc lại và xác minh:
   - bank type là `itembank`;
   - `max_count=1`;
   - số child bằng số component mong đợi;
   - mọi child là `problem`, có parent đúng và upstream đúng;
   - không component nào xuất hiện ở nhiều slot.
7. Nếu một bước lỗi, rollback các node vừa tạo trong request và trả lỗi thật.

## Dọn block sai của các bản cũ

Connector tự dọn **chỉ** các legacy `library_content` block do bản AI cũ tạo, nhận diện bằng block ID bắt đầu `problem-bank-slot-`.

Các Randomized Content Block do giáo viên tạo thủ công không bị xóa.

## UI mới

Trang `/export` được gom thành ba bước:

1. **Tính kế hoạch**
2. **Chuẩn bị thư viện**
3. **Tạo Quiz và Problem Bank**

Các tùy chọn kỹ thuật được ẩn trong phần nâng cao. Nút tạo Quiz chỉ mở khi kế hoạch và thư viện đã sẵn sàng. Luồng chính luôn tạo Unit và native Problem Bank trong một thao tác.

## File chính thay đổi

```text
openedx-connector-plugin/openedx_ai_connector/views.py
backend/app/modules/publisher/service.py
backend/app/core/config.py
backend/app/tests/test_native_itembank_contract.py
backend/app/tests/test_openedx_connector_auth.py
frontend/app/export/page.tsx
frontend/package.json
frontend/package-lock.json
README.md
CHANGELOG.md
```

## Triển khai

### AI Server

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  build --no-cache backend worker frontend

docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --no-deps backend worker frontend

docker compose -f docker-compose.prod.yml --env-file .env.production \
  exec backend alembic upgrade head
```

Bản 14.6 không có migration mới, nhưng lệnh Alembic cần chạy để bảo đảm migration Stable Family `0008` đã áp dụng nếu nâng từ bản cũ hơn.

### CMS connector

Copy plugin mới rồi restart CMS:

```bash
cp openedx-connector-plugin/openedx_ai_connector/views.py \
  /opt/openedx/CMS-FPT/openedx_connector_plugin/openedx_ai_connector/views.py

tutor local restart cms cms-worker
```

Không cần build lại Open edX image nếu plugin đang được mount từ repo.

## Kiểm thử trung thực đã chạy

```text
Python compileall: PASS
Backend pytest: 39 passed, 2 skipped
Frontend typecheck: PASS
Native ItemBank contract test bằng fake Studio handler: PASS
Frontend Next production build: compile/typecheck đã PASS ở các lần chạy;
tiến trình build đầy đủ bị timeout trong môi trường tạo artifact nên không khẳng định build hoàn tất.
```

Hai test skipped là integration test cần Open edX CMS thật.

## Chưa được kiểm thử trong môi trường tạo artifact

- Chưa gọi endpoint insert trên Tutor/Open edX Ulmo.3 thật của người dùng.
- Chưa xác nhận `sync_library_content` thành công với component có asset phức tạp trên server thật.
- Chưa xác nhận rollback native node trên server thật khi một component ở giữa slot lỗi.

Vì vậy sau deploy cần test trước với một course nhỏ, một Unit mới và 2–3 slot.
