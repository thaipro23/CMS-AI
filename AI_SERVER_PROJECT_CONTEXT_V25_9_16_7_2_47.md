# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.50

Baseline mới nhất phải dùng:

```text
v25.9.16.7.2.50 — Bank Quiz Final Test Production QA
zip: ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip
root: ai_server_openedx_v25_9_16_7_2_47
```

Bản `.47` tiếp tục từ `.46` và không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Thay đổi chính `.47`

1. `/bank/quiz` production QA cho flow Quiz/Final test.
2. Final test mặc định `Tạo Final test`; Assignment/ASM mặc định `Không tạo`.
3. Backend `preview_quiz_auto_map` trả thêm trạng thái production cho từng dòng mapping:
   - `READY_TO_CREATE`
   - `MISSING_SECTION`
   - `MISSING_RELEASE`
   - `MISSING_SECTION_AND_RELEASE`
   - `SKIPPED_NO_CREATE`
4. Summary trả `production_gate`, `regular_quiz_count`, `final_test_count`, `missing_section_count`, `missing_release_count`.
5. UI `/bank/quiz` thêm gate strip và cột `Loại`/`Điều kiện`.
6. Dòng `Không tạo` không chặn lưu cấu hình và không yêu cầu Release/Section.

## Các bản được giữ nguyên

- `.46` Analytics SLA Dashboard + Job Observability
- `.45` UAT RollNumber Identity Cleanup
- `.44` RollNumber Identity Reconciliation QA
- `.43` Production Readiness Gate Repair
- `.42` Bank Table Production UX + Bulk Workflow QA
- `.40` CMS Student Username RollNumber Only
- `.37` Analytics Class Result Doctor
- `.36` Responsive Sidebar Shell Fix
- `.35` Analytics Post-Ingest Recalculate Orchestrator

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip -d /tmp/ai-server-v25.9.16.7.2.50
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_47/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```
