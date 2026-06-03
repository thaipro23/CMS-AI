# v25.9.12.12 — Sync UI Safe Fixes

## Mục tiêu
Bản vá an toàn sau v25.9.12.11. Không thay đổi kiến trúc sync/generate lớn.

## Đã sửa
- Không còn xóa message thành công ngay sau khi `loadAll()` reload dữ liệu.
- Chuẩn hóa `NEXT_PUBLIC_API_BASE_URL` để tránh lỗi `/api/api`.
- Đồng bộ version/cache: backend app version, frontend package, `.env.example`, sync fingerprint và prompt version.
- Không cho upload trực tiếp `.doc`/`.xls` legacy; hướng dẫn convert sang `.docx`/`.xlsx` hoặc PDF.
- Bỏ `.doc`/`.xls` khỏi file picker frontend.
- Sửa nút “Thu gọn tất cả” để thu gọn đúng nghĩa.
- Dọn lỗi duplicate `children` trong response tree.

## Cách test nhanh
```bash
docker compose down
docker compose up --build
```

Trên UI `/sync`:
1. Bấm Đồng bộ học liệu khóa học, kiểm tra message thành công còn hiển thị.
2. Upload `.docx` được, `.doc` bị từ chối với thông báo rõ.
3. Nếu env đã là `http://localhost:8081/api`, frontend không gọi thành `/api/api` nữa.
