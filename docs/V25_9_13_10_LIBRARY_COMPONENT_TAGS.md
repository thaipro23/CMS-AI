# v25.9.13.10 - Open edX Library Component Tags

## Mục tiêu

Sau khi AI Server import problem vào Open edX Content Library V2, connector sẽ gắn Open edX Content Tags cho từng component để dropdown **Tags** trong Library UI có dữ liệu.

## Lý do

Các bản trước đã gửi `tag_names` từ AI Server sang CMS connector nhưng connector chưa thật sự ghi tag vào hệ thống Content Tagging của Open edX. Vì vậy Library có component nhưng UI vẫn hiển thị `No tags in current results` và mỗi card có biểu tượng tag `0`.

## Thay đổi chính

File chính:

```txt
openedx-connector-plugin/openedx_ai_connector/views.py
```

Thêm:

- Tạo hoặc lấy taxonomy `AI Learning Check` qua Content Tagging API.
- Gắn taxonomy với Organization của course, ví dụ `FPT`.
- Gắn tags cho từng imported Library problem.
- Tags mặc định gồm:
  - `AI Learning Check`
  - `course:<course-code>`
  - `difficulty:<easy|medium|hard>`
  - `chapter:<chapter-slug>-<hash>`
  - `chapter-title:<tên bài/chương>`
  - `source:<source-slug>-<hash>`
  - `source-type:<type>`
  - `question:<hash>`
- Nếu Content Tagging API không khả dụng, publish vẫn thành công nhưng response trả `tag_result.status=failed_non_fatal` để debug.

## Env mới cho CMS plugin

Các biến này đọc trong CMS/Studio container:

```env
AI_CONNECTOR_TAGGING_ENABLED=true
AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID=ai-learning-check
AI_CONNECTOR_TAG_TAXONOMY_NAME=AI Learning Check
```

Nếu muốn tạm tắt tagging:

```env
AI_CONNECTOR_TAGGING_ENABLED=false
```

## Cách cập nhật

Nếu chỉ sửa plugin, copy file mới:

```txt
openedx-connector-plugin/openedx_ai_connector/views.py
```

vào đúng chỗ plugin trong CMS rồi restart:

```bash
tutor local restart cms cms-worker
```

Không cần build lại AI Server nếu chỉ thay plugin.

## Kiểm tra

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng:

```json
"version": "25.9.13.10"
```

Chạy diagnostics:

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/publish-diagnostics
```

Kỳ vọng có check `content_tagging.api` OK.

Sau đó publish lại một câu approved mới. Trong response `import_result` kỳ vọng có:

```json
"tag_result": {
  "status": "applied",
  "taxonomy_export_id": "ai-learning-check",
  "tag_count": 8
}
```

## Lưu ý

Tags được gắn cho các problem import từ bản này trở đi. Các problem đã import trước đó sẽ không tự có tag nếu chưa republish/import lại.

Nếu Library UI đang mở sẵn, cần reload trang hoặc mở lại popup **Select components** để thấy dropdown tag cập nhật.
