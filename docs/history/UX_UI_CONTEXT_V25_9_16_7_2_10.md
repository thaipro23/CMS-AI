# UX/UI Context v25.9.16.7.2.10

- `/ap-sync` và các màn chọn môn phải hiểu nguồn môn là AP CMS `/api/cms/get-subject-cms`.
- Không hiển thị hoặc mô tả nhầm là lấy từ `get-course`.
- Khi chưa chọn kỳ, UI vẫn có thể lấy catalog môn global nếu backend/AP cho phép.
- Nếu AP subject catalog lỗi, fallback local/env vẫn giữ để không làm dropdown trắng trơ.
