# v25.9.12.9 - Upload File thành node con + Xóa node có confirm

## Mục tiêu
Bản này đổi hành vi upload file vào node theo đúng workflow mới:

- Người dùng chọn một node CMS.
- Upload file bổ sung.
- AI Server tạo **một node con mới** dưới node CMS đã chọn.
- Nội dung file được tách thành chunks nằm dưới node con này.
- Người dùng có thể chọn node con đó để generate Learning Check.
- Người dùng có thể xóa node con upload nếu không cần nữa, nhưng bắt buộc confirm.

## Backend

### Upload file thành node con
Endpoint vẫn giữ:

```http
POST /api/courses/{course_id}/nodes/{node_id}/files
```

Nhưng hành vi đã đổi:

```txt
node CMS cha
└── uploaded_file: File bổ sung: <filename>
    ├── chunk 1
    ├── chunk 2
    └── ...
```

Nếu `replace_existing=true`, cùng một file upload vào cùng một node cha sẽ refresh node con cũ thay vì tạo thêm node trùng. Nếu `replace_existing=false`, mỗi lần upload tạo một node con mới.

### Xóa node con upload
Endpoint mới:

```http
DELETE /api/courses/{course_id}/nodes/{node_id}?confirm=DELETE_NODE
```

Chỉ cho phép xóa node do AI Server tạo khi upload file, ví dụ `block_type=uploaded_file` hoặc `node_id` bắt đầu bằng `ai-upload:`.

Không cho xóa node CMS/Open edX thật từ AI Server để tránh lệch dữ liệu. Nếu muốn xóa học liệu gốc thì xóa trong Studio.

## Frontend
Trang `/sync` đã thêm:

- Nút `Tạo node con từ file`.
- Khi upload xong, UI tự chọn node con mới.
- Node con upload có nút `Xóa node`.
- Khi xóa phải nhập đúng `DELETE_NODE` trong modal xác nhận.

## Dọn dữ liệu cũ
Bản này có guard để khi upload lại cùng file, hệ thống tự xóa các chunks cũ do v25.9.12.8 tạo trực tiếp trên node CMS cha.
