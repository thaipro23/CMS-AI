# v25.9.13.28 - Export / Publish / Review Core Upgrades

Gộp các nâng cấp v25.9.13.20 → v25.9.13.28 theo yêu cầu:

- Problem Bank Friendly Export: `/export` hiển thị Library theo Difficulty, số component và gợi ý cấu hình Problem Bank.
- Publish Reconciliation: sau import gọi lại CMS connector để verify Library/Problem/Tag/Pending state.
- Clean Republish / Replace Existing Component: thêm mode `publish_new`, `replace`, `delete_reimport`.
- Export History + Rollback: lưu batch publish và cho rollback mức AI Server hoặc Open edX best-effort.
- Export UI Workflow: `/export` chuyển thành quy trình 6 bước, bảng Library/status/link/hint.
- Tag Cleanup: chuẩn hóa tối đa 6 tag chính, bỏ `question:<hash>` khỏi tag UI.
- LMS Student View Polish: giữ display_name gọn, bỏ description, solution chỉ hiện sau submit, hint không lộ đáp án.
- Generate/Publish Quality Guard: chặn publish câu có lỗi chất lượng, chuyển sang `needs_review`.
- Source Trace trong Review: nút `Xem nguồn` hiển thị node/chunk/source/publish trace.

## Endpoint mới

```http
GET /api/publish/courses/{course_id}/openedx/history
POST /api/publish/batches/{batch_id}/rollback?level=ai_server
POST /api/publish/batches/{batch_id}/rollback?level=openedx
GET /api/question-bank/{question_id}/source-trace
```

CMS connector mới:

```http
POST /api/ai-connector/v1/libraries/{library_key}/problems/verify
POST /api/ai-connector/v1/libraries/{library_key}/problems/delete
```

## Publish modes

- `publish_new`: chỉ publish câu `approved`, không publish lại câu đã published.
- `replace`: dùng cùng `question_id → openedx_usage_key` để cập nhật component cũ.
- `delete_reimport`: cố gắng xóa component cũ rồi import lại; nếu connector không hỗ trợ delete sẽ ghi warning và tiếp tục replace.

## Cách chạy

AI Server:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

CMS/Studio plugin:

```bash
tutor local restart cms cms-worker
```

Kiểm tra plugin:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng `version=25.9.13.28`.
