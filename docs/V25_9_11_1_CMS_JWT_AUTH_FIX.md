# v25.9.11.1 - CMS JWT Authorization Header Fix

## Vấn đề

Khi Tutor/CMS local trả OAuth token với `token_type = "JWT"`, backend AI Server vẫn gửi token theo dạng:

```http
Authorization: Bearer <jwt-token>
```

Một số API CMS/Open edX sẽ hiểu `Bearer` là opaque OAuth token lưu trong database. Vì JWT không nằm trong bảng token đó, API trả lỗi:

```json
{
  "developer_message": {
    "error_code": "token_nonexistent",
    "developer_message": "The provided access token does not match any valid tokens."
  }
}
```

## Cách sửa

`RealOpenEdXConnector` đọc `token_type` từ response `/oauth2/access_token/` và tự chọn authorization scheme:

- `token_type = JWT` → `Authorization: JWT <token>`
- `token_type = Bearer` hoặc opaque token → `Authorization: Bearer <token>`

Với token nhập tay qua `.env`, connector tự suy đoán:

- Token có 3 phần, ngăn bởi dấu chấm → JWT
- Token còn lại → Bearer

## File đã sửa

- `backend/app/modules/openedx_connector/real.py`
- `backend/app/core/config.py`
- `.env`
- `.env.example`
- `backend/app/tests/test_openedx_connector_auth.py`

## Cấu hình khuyến nghị local

```env
USE_MOCK_OPENEDX=false
OPENEDX_BASE_URL=http://local.openedx.io
OPENEDX_OAUTH_TOKEN_URL=/oauth2/access_token/
OPENEDX_COURSE_BLOCKS_PATH=/api/courses/v2/blocks/
```

## Test nhanh trong backend container

```bash
docker compose exec backend python -c "import os,httpx; base=os.getenv('OPENEDX_BASE_URL').rstrip('/'); token_url=base+os.getenv('OPENEDX_OAUTH_TOKEN_URL','/oauth2/access_token/'); data={'grant_type':'client_credentials','client_id':os.getenv('OPENEDX_CLIENT_ID'),'client_secret':os.getenv('OPENEDX_CLIENT_SECRET'),'token_type':'jwt','scope':'read write'}; token=httpx.post(token_url,data=data,timeout=20).json()['access_token']; r=httpx.get(base+'/api/courses/v2/blocks/',params={'course_id':'course-v1:FPT+DBI102+su26','all_blocks':'true','depth':'all'},headers={'Authorization':'JWT '+token,'Accept':'application/json'},timeout=30); print(r.status_code); print(r.text[:500])"
```

Nếu lệnh trên trả `200`, AI Server `/sync` cũng phải dùng được sau khi build lại.
