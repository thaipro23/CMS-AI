# v25.9.16.7.2.50 — Bank Quiz Final Test Production QA

## Mục tiêu

Bản `.44` đóng rủi ro identity sau khi `.40` đổi chính sách tạo/check tài khoản CMS/Open edX cho sinh viên từ AP username/email sang RollNumber/student_code.

Vấn đề production có thể gặp:

```text
Cũ: CMS/Open edX username = duongcvph59017@fpt.edu.vn
Mới: CMS/Open edX username = ph59017
```

Nếu hệ thống đã từng tạo user cũ, chạy enroll/sync diện rộng ngay có thể tạo trùng người học hoặc lấy nhầm tiến độ. Bản này thêm audit/dry-run để biết lớp nào đang OK, lớp nào còn legacy, dòng nào thiếu RollNumber, dòng nào trùng mã.

Không có migration mới. Giữ nguyên `.43` Production Readiness Gate Repair, `.42` Bank Table Production UX, `.41` action fix, `.40` RollNumber-only CMS username, `.37` Analytics Class Result Doctor, `.36` sidebar fix và `.35` post-ingest recalculate orchestrator.

## Thay đổi chính

1. Backend thêm endpoint read-only:

```text
GET /api/academic/classes/{class_id}/identity-reconciliation
```

2. Endpoint trả về:

```text
- canonical_username: username CMS chuẩn theo RollNumber
- ap_username: username/email AP gốc
- openedx_username: username CMS/Open edX hiện tại trong mapping
- status: OK / READY_FOR_ROLLNUMBER / MISSING_MAPPING / LEGACY_AP_USERNAME / MISSING_ROLLNUMBER / DUPLICATE_ROLLNUMBER / DUPLICATE_CMS_MAPPING / CMS_USERNAME_MISMATCH / CANONICAL_INACTIVE
- severity: blocker / warning / info
- recommended_action
- blockers / warnings
```

3. UI chi tiết lớp thêm panel:

```text
Kiểm tra identity CMS/RollNumber
```

Panel này hiển thị:

```text
- Tổng dòng
- Sẵn sàng
- Blocker
- Cảnh báo
- Legacy AP username
- Thiếu mapping
- Việc cần làm tiếp theo
- 5 dòng mẫu để kiểm tra nhanh
```

4. Không mutate dữ liệu:

```text
mutation_performed = false
dry_run = true
```

Bản này không tự sửa mapping, không xóa user cũ, không đổi user Open edX. Nó chỉ giúp admin biết có an toàn để chạy Đồng bộ full CMS/Ghi danh CMS diện rộng hay chưa.

## Deploy

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip -d /tmp/ai-server-v25.9.16.7.2.50

rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_47/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Env production nên set rõ

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Test sau deploy

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/academic/classes/<CLASS_ID>/identity-reconciliation?page_size=200' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Kỳ vọng:

```text
- Nếu mapping đã là ph59017: status OK.
- Nếu mapping còn duongcvph59017@fpt.edu.vn: status LEGACY_AP_USERNAME, severity blocker.
- Nếu chưa có mapping nhưng có RollNumber: READY_FOR_ROLLNUMBER hoặc MISSING_MAPPING.
- Nếu thiếu RollNumber: MISSING_ROLLNUMBER, severity blocker.
```
