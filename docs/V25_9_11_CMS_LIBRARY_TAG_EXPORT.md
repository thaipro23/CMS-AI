# v25.9.11 - CMS Library Ensure + Filter Tags + OLX Cleanup

## Nội dung sửa

Bản này sửa luồng publish OLX để phù hợp yêu cầu triển khai CMS thật:

1. Trước khi import problem, hệ thống resolve đúng thư viện theo `course + chapter/module + difficulty`.
2. Connector phải kiểm tra thư viện đã tồn tại chưa; nếu chưa có thì tạo, nếu có rồi thì dùng lại.
3. Mỗi câu hỏi gửi kèm `tag_names` để lọc trong CMS Library UI.
4. Metadata nội bộ không còn nhét vào XML OLX, tránh rủi ro parser/import.
5. Publish lại câu đã `published` bị chặn để tránh duplicate, trừ khi sau này có workflow revision/force republish.
6. Exporter validate dữ liệu cuối trước khi sinh OLX.

## File chính

```txt
backend/app/services/cms_tags.py
backend/app/services/openedx_exporter.py
backend/app/modules/publisher/service.py
backend/app/modules/openedx_connector/base.py
backend/app/modules/openedx_connector/mock.py
backend/app/modules/openedx_connector/real.py
openedx-connector-plugin/openedx_ai_connector/views.py
docs/CMS_LIBRARY_TAG_EXPORT.md
```

## Tag mặc định

```txt
AI Learning Check
course:<course-code>
chapter:<chapter-slug>-<hash>
chapter-title:<chapter-title>
difficulty:easy|medium|hard
source:<source-title-slug>-<hash>
source-type:html|transcript|file|problem
question:<short-id-hash>
topic:<ai/user tag nếu có>
```

## Kết quả mong muốn trong CMS

Khi vào thư viện như màn hình CMS Library:

- Nếu library đã có, hệ thống không tạo thêm library trùng.
- Nếu chưa có, hệ thống tạo library đúng tên chương/bài/difficulty.
- Câu hỏi import vào library có tag để lọc theo `difficulty`, `source`, `chapter`, `source-type`.
- Giáo viên dùng filter `Tags` để chọn đúng nhóm câu khi tạo ngân hàng câu hỏi/random.
