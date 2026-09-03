# Verification — Import Quiz CMS cũ SU26

Ngày kiểm tra gần nhất: 2026-09-03.

## Kết quả đạt

| Gate | Kết quả |
|---|---|
| Ruff trên toàn bộ file backend thay đổi | PASS |
| Test importer + canonical content + Open edX exporter | 36 passed |
| Security gate không trả raw exception qua route | PASS |
| FastAPI route registration | 3/3 route tồn tại, gồm `skip-errors` |
| Frontend TypeScript | PASS |
| Frontend ESLint, zero warning | PASS |
| Next.js production build | PASS, 36/36 static pages; route `/import-quiz-cms-old` có trong output |
| Legacy flexible Quiz planner regression | PASS; 5 câu chưa phân loại được dùng đúng một lần trong 3 slot Easy/Medium/Hard |
| Import + exporter + quota + route security regression mới nhất | 39 passed |

## Đối chiếu file mẫu thật

| File | Kết quả parser/preview |
|---|---|
| HOS2032 | 11 sheet, 308 câu; 165 single, 61 multi, 82 dropdown; 308 chưa phân loại và được phép xếp linh hoạt; có thể commit |
| MEC129 | 8 sheet, 406 câu; 350 single, 56 multi; 312 easy, 93 medium, 1 chưa phân loại; 6 nhóm câu trùng chỉ cảnh báo; có thể commit |
| MEC229 | 8 sheet, 224 câu; 37 câu lỗi (36 câu thiếu ảnh, 1 câu đáp án trùng); preview ban đầu bị chặn; chọn Bỏ qua còn 187 câu, 0 lỗi và có thể commit |

Ba workbook thật được đọc lại bằng parser sau thay đổi: tổng 938 câu; HOS2032 và MEC229 không bị gán nhầm thành `medium` khi thiếu cột độ khó.

## Full historical suite

Toàn bộ thư mục `backend/app/tests` không phải một gate sạch cho baseline ZIP này: kết quả là 570 passed, 2 skipped, 261 failed. Các lỗi chủ yếu là test lịch sử khóa nhiều version cũ mâu thuẫn nhau, integration test thiếu PostgreSQL/Redis/Alembic runtime, và các UI contract cũ vốn không khớp source baseline hiện tại. Vì vậy sign-off của tính năng dùng targeted regression ở trên; không diễn giải full historical suite là regression của importer.

## Chưa xác nhận trong môi trường này

- Browser UAT bằng tài khoản CMS thật theo từng role.
- Worker chạy với Redis/PostgreSQL/MinIO production thật.
- Import MEC229 đủ 224 câu vì bộ ảnh companion chưa được cung cấp và dòng 238 cần sửa dữ liệu nguồn. Nhánh bỏ qua 37 câu lỗi đã được kiểm thử, còn 187 câu hợp lệ.
