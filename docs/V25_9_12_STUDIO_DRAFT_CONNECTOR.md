# v25.9.12 - CMS Studio Draft Connector

## Mục tiêu

Bản này đổi hướng sync học liệu từ learner-facing Course Blocks API sang connector chạy trong CMS/Studio trước. Lý do: Course Blocks API chủ yếu trả cây khóa học đã publish; không đọc đủ bản nháp trong Studio, problem XML cũ, và tài liệu đính kèm trong học liệu.

## Luồng mới

AI Server khi gọi `/api/courses/sync` sẽ thử endpoint trong CMS trước:

```http
GET /api/ai-connector/v1/courses/{course_id}/studio-content?include_drafts=true&include_assets=true&include_problems=true
```

Nếu endpoint này chưa cài hoặc lỗi, AI Server fallback về Course Blocks API:

```http
GET /api/courses/v2/blocks/
```

## Dữ liệu connector Studio cố gắng lấy

- Course tree từ modulestore.
- Draft branch trước, published branch sau nếu draft không có.
- HTML raw content trong Studio.
- Problem/quiz cũ dạng OLX/XML từ `problem.data`.
- Video metadata và các trường transcript/video liên quan.
- Link tài liệu đính kèm trong HTML/problem content, ví dụ PDF/PPTX/DOC/TXT.
- Course static assets nếu contentstore API của bản CMS hiện tại hỗ trợ.

## Cấu hình AI Server

```env
OPENEDX_STUDIO_CONTENT_ENDPOINT=/api/ai-connector/v1/courses/{course_id}/studio-content
OPENEDX_PREFER_STUDIO_CONTENT=true
```

## Lưu ý triển khai Tutor local

Phải cài `openedx-connector-plugin` vào image Open edX/Tutor, sau đó restart/rebuild CMS/LMS. Nếu chưa cài plugin, AI Server vẫn sync được cây khóa học qua Course Blocks API nhưng sẽ không lấy đủ draft, old questions và assets.

## Trạng thái publish/library

Bản này tập trung vào đọc học liệu từ Studio. Các endpoint ensure library/import OLX vẫn giữ contract v25.9.11: check library trước, có rồi dùng lại, chưa có thì tạo, gửi tag_names để lọc sau khi plugin production áp dụng taxonomy/tag thật.
