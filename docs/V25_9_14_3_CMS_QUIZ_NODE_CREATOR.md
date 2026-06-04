# v25.9.14.3 — CMS Quiz Node Creator

## Mục tiêu

Bản này thêm bước tạo **Quiz node thật trong Open edX Studio/CMS** từ kế hoạch Family Slot Problem Bank của AI Server.

Luồng mong muốn:

1. Giáo viên chọn course đã sync.
2. Giáo viên chọn node cha trong cây CMS: `course`, `chapter` hoặc `sequential`.
3. AI Server tính Family Slot Plan.
4. Giáo viên sửa plan trên UI.
5. Giáo viên bấm **Tạo Quiz trên Open edX**.
6. AI Server gọi CMS connector để tạo draft XBlock thật trong Studio.

Bản này **chưa tự insert Problem Bank blocks**. Phần đó để cho v25.9.14.4.

## Nguyên tắc trung thực / production-safe

Không có fake success:

- Nếu `USE_MOCK_OPENEDX=true`, backend chặn tạo Quiz node.
- CMS connector phải trả về `usage_key` thật từ modulestore.
- Nếu Open edX/modulestore không hỗ trợ `create_child`, connector trả lỗi 502 kèm diagnostics.
- Nếu chọn sai loại node, API trả lỗi rõ ràng.

## API mới trong AI Server

```http
POST /api/publish/courses/{course_id}/cms-quiz-node/create
```

Payload:

```json
{
  "parent_node_id": "block-v1:FPT+MUL211+SU26+type@chapter+block@bai_2",
  "quiz_title": "AI Learning Check - Bài 2",
  "unit_title": "Quiz tự luyện",
  "plan": {
    "slots": []
  }
}
```

Response thành công:

```json
{
  "ok": true,
  "created": true,
  "status": "created_or_existing",
  "created_nodes": [
    {
      "usage_key": "block-v1:...+type@sequential+block@ai-learning-check...",
      "block_type": "sequential",
      "display_name": "AI Learning Check - Bài 2",
      "created": true
    },
    {
      "usage_key": "block-v1:...+type@vertical+block@quiz-tu-luyen...",
      "block_type": "vertical",
      "display_name": "Quiz tự luyện",
      "created": true
    }
  ],
  "leaf_unit_node_id": "block-v1:...+type@vertical+block@quiz-tu-luyen...",
  "manual_publish_required": true,
  "problem_bank_auto_inserted": false
}
```

## API mới trong CMS connector

```http
POST /api/ai-connector/v1/courses/{course_id}/quiz-nodes
```

Endpoint này chạy trong Studio/CMS và dùng modulestore draft `create_child` để tạo node thật.

Cấu trúc tạo theo loại node cha:

| Node cha | Node được tạo |
|---|---|
| `course` | `chapter` → `sequential` → `vertical` |
| `chapter` | `sequential` → `vertical` |
| `sequential` | `vertical` |
| `vertical` | Không hỗ trợ trong v25.9.14.3 |

## UI mới

Trang `/export` có khối **Tạo Quiz node trên Open edX**:

- Dropdown chọn node cha CMS đã sync.
- Chỉ hiện node type `course`, `chapter`, `sequential`.
- Nhập tên mục Quiz.
- Nhập tên Unit.
- Bấm **Tạo Quiz trên Open edX**.
- Sau khi tạo, UI hiển thị usage key thật của các node đã tạo hoặc node đã tồn tại.

## Env mới

```env
OPENEDX_QUIZ_NODE_CREATE_ENDPOINT=/api/ai-connector/v1/courses/{course_id}/quiz-nodes
```

## Cách chạy

Nếu chỉ sửa CMS connector plugin:

```bash
# Copy plugin đã sửa vào CMS nếu đang mount/fork riêng
# Sau đó restart CMS và CMS worker
tutor local restart cms cms-worker
```

Nếu sửa AI Server backend/frontend:

```bash
docker compose build --no-cache backend worker frontend
docker compose up -d
```

Migration không bắt buộc vì bản này không thêm bảng mới.

## Cách test thật

1. Kiểm tra CMS connector:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

2. Sync course trong `/sync` để có cây node mới nhất.

3. Vào `/export`, chọn một node `chapter` hoặc `sequential`.

4. Tính plan:

```http
POST /api/publish/courses/{course_id}/family-bank-plan/preview
```

5. Tạo Quiz node:

```http
POST /api/publish/courses/{course_id}/cms-quiz-node/create
```

6. Mở Studio/CMS kiểm tra node draft mới xuất hiện dưới node đã chọn.

7. Nếu API trả `created=false`, kiểm tra xem node cùng tên đã tồn tại hay chưa; connector đang reuse node theo display name để tránh double-click tạo trùng.

## Giới hạn hiện tại

- Chưa tạo Problem Bank blocks.
- Chưa tự gắn variants vào Problem Bank.
- Chưa publish course/unit thay giáo viên.
- Nếu chọn `vertical`, API báo lỗi vì v25.9.14.3 chỉ tạo container quiz. v25.9.14.4 mới xử lý insert block vào Unit.

## Bước tiếp theo

v25.9.14.4 — Problem Bank Auto Insert:

- Mỗi slot trong Family Bank Plan trở thành một Problem Bank block.
- Mỗi Problem Bank block random 1 component.
- Nếu slot gộp 2 family, block chứa variants của 2 family đó.
- AI Server phải verify sau insert và không được báo thành công giả.
