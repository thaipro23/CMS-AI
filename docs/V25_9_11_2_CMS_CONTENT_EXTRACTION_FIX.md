# v25.9.11.2 - CMS Course Content Extraction Fix

## Mục tiêu

Bản này sửa luồng sync CMS local sau khi OAuth/JWT đã hoạt động nhưng Course Blocks API chỉ trả course tree, chưa tạo được chunk học liệu thật.

## Thay đổi chính

1. `RealOpenEdXConnector.get_course_blocks()` gửi thêm nhiều tham số `student_view_data`:
   - `html`
   - `video`
   - `problem`

2. Video block có transcript URL sẽ được AI Server tự tải nội dung transcript về.
   - Trước: `content` chỉ là link `/transcript/download?lang=en`.
   - Sau: `content` là text transcript thật để chunking/generate dùng được.

3. HTML block không còn biến message cấu hình thành chunk học liệu.
   - Nếu CMS trả `{enabled:false, message:"To enable..."}` thì connector bỏ qua.
   - Muốn lấy HTML content thật, cần bật `FEATURES["ENABLE_HTML_XBLOCK_STUDENT_VIEW_DATA"] = True` trong Tutor/CMS.

4. Transcript JSON/SRT/VTT/plain text được normalize thành plain text.

## Lưu ý test local

Sau khi chạy bản này, nếu course có video transcript URL thì `/sync` có thể tạo chunk transcript ngay cả khi HTML student view data chưa bật.

Nếu muốn lấy HTML component thật, bật Tutor patch:

```python
from tutor import hooks

hooks.Filters.ENV_PATCHES.add_item((
    "openedx-lms-common-settings",
    """
FEATURES["ENABLE_HTML_XBLOCK_STUDENT_VIEW_DATA"] = True
"""
))
```

Sau đó:

```bash
tutor plugins enable enable_html_student_view_data
tutor config save
tutor local reboot -d
```

## Test nhanh

```bash
docker compose down
docker compose up --build
```

Vào `/sync`, sync lại course. Sau đó kiểm tra `/chunks/page`, source type `transcript` phải có chunk nếu transcript download thành công.
