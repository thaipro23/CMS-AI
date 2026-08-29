# Verification — Import Quiz CMS cũ SU26

Ngày kiểm tra: 2026-08-29.

## Kết quả đạt

| Gate | Kết quả |
|---|---|
| Ruff trên toàn bộ file backend thay đổi | PASS |
| Test importer + canonical content + Open edX exporter | 35 passed |
| Security gate không trả raw exception qua route | PASS |
| FastAPI route registration | 2/2 route tồn tại |
| Frontend TypeScript | PASS |
| Frontend ESLint, zero warning | PASS |
| Next.js production build | PASS, 36/36 static pages; route `/import-quiz-cms-old` có trong output |

## Đối chiếu file mẫu thật

| File | Kết quả parser/preview |
|---|---|
| HOS2032 | 11 sheet, 308 câu; 165 single, 61 multi, 82 dropdown; 308 medium; có thể commit |
| MEC129 | 8 sheet, 406 câu; 350 single, 56 multi; 312 easy, 94 medium; 6 nhóm câu trùng chỉ cảnh báo; có thể commit |
| MEC229 | 8 sheet, 224 câu; 171 single, 53 multi; 224 medium; 6 nhóm câu trùng; 36 tham chiếu ảnh chưa có asset; 1 lỗi lựa chọn trùng tại `Quiz 01`, dòng 238; bị chặn đúng thiết kế |

## Full historical suite

Toàn bộ thư mục `backend/app/tests` không phải một gate sạch cho baseline ZIP này: kết quả là 570 passed, 2 skipped, 261 failed. Các lỗi chủ yếu là test lịch sử khóa nhiều version cũ mâu thuẫn nhau, integration test thiếu PostgreSQL/Redis/Alembic runtime, và các UI contract cũ vốn không khớp source baseline hiện tại. Vì vậy sign-off của tính năng dùng targeted regression ở trên; không diễn giải full historical suite là regression của importer.

## Chưa xác nhận trong môi trường này

- Browser UAT bằng tài khoản CMS thật theo từng role.
- Worker chạy với Redis/PostgreSQL/MinIO production thật.
- Import MEC229 hoàn chỉnh vì bộ ảnh companion chưa được cung cấp và dòng 238 cần sửa dữ liệu nguồn.
