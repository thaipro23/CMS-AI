# v25.9.16.7.2.50 — Bank Quiz Final Test Production QA

## Mục tiêu

Bản này tiếp tục từ `.46` và tập trung làm `/bank/quiz` đủ rõ cho UAT/production flow tạo Quiz/Final test từ ngân hàng đề.

Mục tiêu là tránh tạo nhầm, tránh hiểu sai Final test/Assignment, và không để người vận hành phải đoán vì sao một dòng chưa thể tạo bài kiểm tra.

## Thay đổi chính

- Final test mặc định `Tạo Final test`.
- Assignment/ASM mặc định `Không tạo`.
- Backend auto-map trả thêm production status cho từng dòng.
- Summary trả `production_gate`, `regular_quiz_count`, `final_test_count`, `missing_section_count`, `missing_release_count`.
- UI `/bank/quiz` thêm gate strip: Quiz, Final test, Không tạo, Thiếu Section, Thiếu Release, Gate.
- Bảng map thêm cột `Loại` và `Điều kiện`.
- Cột STT và thao tác trong bảng map được sticky để dễ vận hành trên course nhiều bài.
- Dòng `Không tạo` không yêu cầu Release/Section và không chặn lưu cấu hình.
- Không có migration mới.

## Env nên set

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip -d /tmp/ai-server-v25.9.16.7.2.50
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_47/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Verify nhanh

1. Mở `/bank/quiz`.
2. Dán Course ID Open edX.
3. Kiểm tra Final test phải mặc định `Tạo Final test`.
4. Assignment/ASM phải mặc định `Không tạo`.
5. Gate phải chỉ rõ thiếu Section hay Release.
6. Dòng `Không tạo` không được chặn `Lưu cấu hình`.

## Không thay đổi

- Không có Alembic migration mới.
- Không đổi thuật toán tạo câu hỏi.
- Không đổi RollNumber identity cleanup.
- Giữ `.46` Analytics SLA Dashboard, `.45` UAT RollNumber cleanup, `.44` identity reconciliation, `.43` readiness repair, `.42` Bank Table Production UX.
