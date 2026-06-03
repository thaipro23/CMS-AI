# v25.9.12.8 - File/Handout Extraction + Upload File vào Node

## Mục tiêu
Bản này xử lý hai luồng file:

1. CMS/Studio handout/link asset: connector phát hiện link `/asset-v1:...block@filename.ext`, tải file best-effort và trả metadata/bytes về AI Server.
2. Giáo viên chọn một node trong cây nội dung rồi upload file bổ sung vào node đó. File được tách text thành chunks và dùng làm nguồn generate Learning Check, không ghi ngược vào Open edX.

## Định dạng hỗ trợ
- PDF: `.pdf`
- PowerPoint: `.pptx`/`.ppt` nếu `python-pptx` mở được
- Word: `.docx`
- Excel: `.xlsx`, `.xlsm`
- CSV/TSV: `.csv`, `.tsv`
- Text: `.txt`, `.md`, `.markdown`, `.html`, `.htm`, `.json`, `.xml`, `.srt`, `.vtt`

Office legacy `.doc` và `.xls` được nhận diện nhưng không parse ổn định trong Python thuần. Nên đổi sang `.docx`, `.xlsx` hoặc PDF.

## Backend mới
Endpoint:

```http
POST /api/courses/{course_id}/nodes/{node_id}/files
Content-Type: multipart/form-data
```

Form fields:

```txt
file=<binary>
replace_existing=true|false
```

Kết quả: file được gắn vào `block_id=node_id`, source_ref dạng `uploaded://{node_id}/{filename}`.

## Frontend mới
Trang `/sync` có khu vực `Upload file bổ sung vào node này` trong panel `Nội dung node được chọn`.

## Connector plugin
`openedx-connector-plugin/openedx_ai_connector/views.py` đã thêm:

- đọc `handout` singular trên Video XBlock;
- quét link `asset-v1` từ raw HTML/content;
- lấy filename thật sau `block@`;
- trả `bytes_base64` best-effort cho asset dưới 15MB;
- bỏ serialize callable/method như `VideoStudentViewHandlers.transcript`.
