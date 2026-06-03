# v25.9.13.6 - Content Library Organization Fix

## Mục tiêu

Sửa lỗi publish thật sang Open edX Content Libraries V2 khi CMS trả:

```txt
AssertionError tại create_library(...)
assert isinstance(org, Organization)
```

## Nguyên nhân

Ở bản 25.9.13.5, connector truyền `org='FPT'` dạng chuỗi vào API `create_library`. Trên Open edX/Tutor Ulmo, API này yêu cầu `org` là instance thật của model `organizations.models.Organization`, không phải string. Vì vậy API assert và trả 502.

## Sửa đổi

File chính:

```txt
openedx-connector-plugin/openedx_ai_connector/views.py
```

Thêm helper `_organization_for_library(...)` để:

- lấy org từ `course-v1:FPT+DBI102+su26` thành `FPT`;
- tìm `Organization(short_name='FPT')` hoặc case-insensitive;
- truyền object `Organization` thật vào `create_library`;
- nếu không tìm thấy org, trả lỗi rõ danh sách org hiện có;
- cho phép auto-create org khi bật env `AI_CONNECTOR_AUTO_CREATE_ORG=true` cho local/dev.

## Env mới trong CMS/Studio plugin

```env
AI_CONNECTOR_AUTO_CREATE_ORG=false
```

Không nên bật ở production nếu chưa kiểm soát org. Với local test có thể bật tạm.

## Kiểm tra

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Kỳ vọng:

```json
{
  "version": "25.9.13.6",
  "publish_implementation": "content_libraries_v2_python_api",
  "stub_publish": false
}
```

Kiểm tra org trong CMS:

```bash
tutor local run cms ./manage.py cms shell -c "from organizations.models import Organization; print(list(Organization.objects.all().values_list('short_name','name')[:50]))"
```

Nếu chưa có org `FPT`, tạo:

```bash
tutor local run cms ./manage.py cms shell -c "from organizations.models import Organization; Organization.objects.get_or_create(short_name='FPT', defaults={'name':'FPT'})"
```
