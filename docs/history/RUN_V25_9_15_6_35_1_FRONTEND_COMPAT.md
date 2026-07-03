# v25.9.15.6.35.1 - Frontend Compatibility Hotfix for BE .33-.35

Mục tiêu: chưa làm `v25.9.15.6.36 Lightweight Question DTO`. Bản này chỉ rà soát và sửa FE để chạy ổn với backend mới sau các bản:

- `.31.13` Bank Business RBAC
- `.33` Pagination Contract
- `.34` Dashboard Summary Engine
- `.35` Bank Search Engine

## Sửa chính

1. `frontend/lib/api.ts`
   - `getBankVersionQuestions()` không còn gửi `limit=300` trực tiếp lên BE.
   - BE mới giới hạn `limit <= 100`, nên FE tự fetch cursor pages 100 câu/lần cho đến đủ số lượng UI yêu cầu.
   - `searchBankDashboard()` hiểu response grouped mới từ `/api/question-bank-v2/search` và vẫn fallback được với response cũ.

2. `frontend/context/AppContext.tsx`
   - Sau khi có AI JWT, FE gọi `/api/rbac/me` để lấy business permissions.
   - `can()` giờ hiểu cả legacy permission cũ và permission nghiệp vụ mới như `subject.create`, `subject.update`, `question.generate`, `bank.release.publish`.
   - FE không còn chỉ dựa vào role legacy `teacher/reviewer/admin`, tránh việc Trưởng bộ môn/Chủ môn bị khóa nút sai.

3. `frontend/app/bank/_components/BankPages.tsx`
   - Nút tạo/sửa môn dùng `subject.create` / `subject.update`.
   - Nút tạo/sửa version môn dùng `subject.update`.
   - Nút tạo/sửa bài dùng `subject.update`.
   - Nút tạo/sửa bộ môn vẫn giữ `manage_settings` để chỉ admin hệ thống thao tác.

## Kiểm tra đã chạy

```bash
cd frontend
npm ci --offline --ignore-scripts --no-audit --no-fund
npm run typecheck
```

Kết quả: `tsc --noEmit` pass.

Tôi có thử `npm run build`, nhưng trong sandbox lệnh dừng ở bước `Creating an optimized production build ...` đến timeout. Vì vậy chưa claim Next production build pass trong sandbox. Trên server thật hãy build Docker để xác nhận cuối.

## Deploy

```bash
cd /opt/ai-server

docker compose -f docker-compose.prod.yml --env-file .env.production build frontend

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate frontend
```

Nếu muốn deploy cả backend cho đồng bộ version:

```bash
cd /opt/ai-server

docker compose -f docker-compose.prod.yml --env-file .env.production build backend worker frontend

docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

## Test nhanh sau deploy

1. Đăng nhập bằng user `SYSTEM_ADMIN`:
   - thấy `/users`, `/settings`
   - tạo/sửa bộ môn được

2. Đăng nhập bằng `DEPARTMENT_HEAD`:
   - thấy môn trong bộ môn mình
   - tạo/sửa môn, version, bài trong bộ môn được
   - không tạo/sửa bộ môn khác

3. Đăng nhập bằng `SUBJECT_OWNER`:
   - tạo/sửa version/bài trong môn mình được
   - gán reviewer trong scope của mình được

4. Mở `/bank/chapters/{chapterId}`:
   - không còn lỗi `422` khi FE cần lấy hơn 100 câu hỏi
   - FE tự fetch cursor nhiều trang nếu UI yêu cầu 300 câu

5. Quick search:

```bash
curl -s "http://api-ai.cms-test.poly.edu.vn/api/question-bank-v2/search?q=WEB107&limit=20&include_questions=true" \
  -H "Authorization: Bearer <AI_TOKEN>" | python3 -m json.tool
```

FE phải hiển thị kết quả từ `items`, hoặc fallback từ `groups` nếu cần.
