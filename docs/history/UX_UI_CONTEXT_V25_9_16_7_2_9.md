# UX/UI Context v25.9.16.7.2.9 — AP Campus Map Payload + STT Sweep

## AP Campus

Lỗi user thấy không phải AP chết. `curl` chứng minh AP trả đúng dữ liệu, nhưng payload `data` là object map `{code: name}`. Backend cũ chỉ đọc list nên normalize thành rỗng và audit báo sai.

UI sau fix:
- `/premises` đồng bộ được Poly/PTCĐ từ AP CMS.
- `/ap-sync` không còn báo thiếu cơ sở nếu AP trả object map hợp lệ.

## STT tables

Đã rà toàn bộ TSX:
- Bảng có header `STT` phải có cell `.stt-cell` trong body.
- Sửa 3 bảng còn thiếu body STT.
- Giữ sticky STT theo CSS từ bản 7.2.7.

## Không đổi

- Không migration.
- Không reset DB.
- Không xóa volume.
- Không đổi secret/env thật.
