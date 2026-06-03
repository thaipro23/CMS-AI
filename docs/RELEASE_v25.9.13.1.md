# v25.9.13.1 - OCR PSM Fix

## Mục tiêu

Sửa lỗi OCR PDF scan/screenshot chỉ đọc được tiêu đề lớn, ví dụ chỉ ra `Open edX Verawood - June 2026 Release` mà bỏ qua đoạn chữ nhỏ bên dưới.

## Thay đổi chính

- Thêm `FILE_OCR_TESSERACT_CONFIG`, mặc định `--oem 3 --psm 6`.
- `_ocr_image()` dùng PSM 6 để coi ảnh là một block text thống nhất, phù hợp với slide/screenshot/PDF scan.
- Thêm fallback PSM 11 và chọn kết quả OCR dài nhất.
- Tiền xử lý ảnh sang grayscale trước khi OCR để ổn định hơn với ảnh nền tối.
- Đồng bộ version/cache lên `25.9.13.1`.

## Env mới

```env
FILE_OCR_ENABLED=true
FILE_OCR_LANGUAGE=vie+eng
FILE_OCR_MAX_PAGES=20
FILE_OCR_TESSERACT_CONFIG=--oem 3 --psm 6
```

## Test nhanh

```bash
docker compose build --no-cache backend worker
docker compose up
```

Upload lại PDF scan/screenshot và kiểm tra node detail.
