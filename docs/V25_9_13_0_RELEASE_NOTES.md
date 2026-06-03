# v25.9.13.0 — Advanced File Extraction: OCR + PPTX Notes

## Mục tiêu
Nâng cấp extractor để đọc tốt hơn học liệu thật: PDF scan, ảnh trong slide và speaker notes trong PowerPoint.

## Đã thêm
- PDF text vẫn dùng `pypdf` như cũ.
- Nếu PDF page không có text và `FILE_OCR_ENABLED=true`, backend thử OCR page scan bằng PyMuPDF hoặc pdf2image + Tesseract.
- PPTX đọc thêm speaker notes từ `ppt/notesSlides`.
- PPTX có thể OCR ảnh trong slide nếu bật đồng thời:
  - `FILE_OCR_ENABLED=true`
  - `PPTX_OCR_IMAGES_ENABLED=true`
- Docker backend thêm `tesseract-ocr`, `tesseract-ocr-vie`, `poppler-utils`.
- Python deps thêm `pillow`, `pytesseract`, `pdf2image`, `PyMuPDF`.

## Mặc định an toàn
OCR mặc định tắt để tránh chậm và tránh lỗi nếu môi trường production chưa cài Tesseract/Poppler.

## Env mới
```env
FILE_OCR_ENABLED=false
FILE_OCR_LANGUAGE=vie+eng
FILE_OCR_MAX_PAGES=20
PPTX_EXTRACT_SPEAKER_NOTES=true
PPTX_OCR_IMAGES_ENABLED=false
```

## Cách test
1. Build lại backend/worker:
```bash
docker compose build --no-cache backend worker
docker compose up
```
2. Upload PDF scan hoặc PPTX có notes vào node.
3. Nếu muốn OCR, bật env rồi build/restart lại.
