# Release v25.9.16.7.2.50 — UAT Evidence Pack + Acceptance Report Export

## Mục tiêu

Bản này biến các kiểm tra UAT analytics rời rạc thành một gói bằng chứng có thể lưu lại và gửi cho đội vận hành/QA.

## Thay đổi chính

- Thêm endpoint read-only `GET /api/analytics/ops/evidence-pack`.
- Endpoint gom các báo cáo đã có:
  - Production readiness.
  - Analytics SLA.
  - Pilot acceptance.
  - Class doctor nếu truyền `class_id`.
- Thêm script `scripts/analytics-uat-evidence-pack.sh` để xuất JSON + Markdown report.
- `/analytics/learning` hiển thị panel `Gói bằng chứng UAT`.

## Cam kết an toàn

Endpoint/script này:

- Không đọc raw `tracking.log` trong request.
- Không enqueue job.
- Không recalculate.
- Không mutate dữ liệu.
- Không kết luận vi phạm cá nhân.

## Chạy evidence pack

```bash
cd /opt/ai-server

API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
CLASS_ID='<CLASS_ID>' \
OUT_DIR=/tmp/ai-analytics-evidence-$(date +%Y%m%d-%H%M%S) \
./scripts/analytics-uat-evidence-pack.sh
```

Kết quả:

```text
build.json
readiness.json
rbac-scope-audit.json
analytics-sla.json
pilot-acceptance.json
evidence-pack.json
class-doctor.json
EVIDENCE_SUMMARY.md
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.50-uat-evidence-pack-report-export.zip -d /tmp/ai-server-v25.9.16.7.2.50
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_50/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Env version

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Migration

Không có migration mới. Latest vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
