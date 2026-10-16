# CMS-AI: hướng dẫn tiếp tục nhanh

AI thực hiện vai trò **Principal Software Architect / Technical Lead / Senior
Software Engineer**. Trước khi sửa code, đọc [tiêu chuẩn kỹ thuật](docs/ENGINEERING_STANDARDS.md):
review edge case, quyền, dữ liệu, race/retry và hiệu năng; kiểm chứng theo rủi ro,
không tự cam kết “không có bug”. Mỗi phiên bản/hotfix/bàn giao phải cập nhật
`docs/CURRENT_STATE.md`, tài liệu/index liên quan và catalog trước khi báo hoàn thành.

Scope: repository `thaipro23/CMS-AI`, nhánh nghiệp vụ `feat/import-quiz-cms-old-su26`.
Git checkout và yêu cầu hiện tại quyết định scope; không tự checkout/reset/pull khi có local changes.

1. Đọc `git status --short`; chạy `python scripts/repo_index.py check`.
2. Đọc `CODE_INDEX.md`; mở **một** mục liên quan trong `docs/INDEX.md`.
3. Tra `python scripts/repo_index.py find "cac tu trong duong dan" --limit 10`
   hoặc `ls <directory>`; dùng `rg` trong scope đã chọn. Không quét toàn repo mặc định.
4. Chỉ cần tình trạng bàn giao thì đọc `docs/CURRENT_STATE.md`. Snapshot có mốc Git;
   production cần bằng chứng image/runtime riêng. Nếu index stale/dirty, xem file đổi
   và cập nhật theo `docs/REPO_INDEX.md`; không tin bản đồ cũ như source hiện tại.

Không đọc toàn bộ `docs/_index/catalog.json`, `docs/history/`, `AI_SERVER_PROJECT_*`,
`RUN_V*`, `RELEASE_v*`, `VERIFICATION_v*`, `docs/superpowers/` khi khởi động.
Chúng là lịch sử/thiết kế, chỉ mở đúng tài liệu liên quan.

Ràng buộc: API/service thực thi RBAC; Bank và vận hành đào tạo giữ scope riêng;
campus sync lấy danh mục thủ công `/premises`; identity sinh viên dùng RollNumber/
`student_code` đúng case. Không dùng AP username/email thay thế tùy tiện.
AI quota chỉ tính câu AI, không tính manual/import. Công việc nặng đi qua job/worker.
Không suy ra deploy từ commit hoặc lời hứa trong chat. Không xóa dữ liệu/PVC,
flush Redis, purge queue hoặc sửa trạng thái job/migration để che lỗi.

Khi đổi đường dẫn/module, sửa index người đọc; sau commit source, build và commit
catalog metadata. Lệnh và phạm vi kiểm tra: `docs/REPO_INDEX.md`.
