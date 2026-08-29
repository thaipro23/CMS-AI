# Verification v25.9.16.7.2.64.16.5.7.2.18

## Kết quả đã xác nhận trong workspace

### Release/static gates

- Claude review pack cuối: **34 PASS / 0 FAIL / 0 WARN**.
- UAT build gate local cuối: **43 PASS / 0 FAIL / 3 WARN**.
- Full frontend design contract: **30/30 PASS**.
- Active `.18` + frontend/RBAC contract tests: **27/27 PASS** bằng SQLite test DB.
- Sonar/worker/question-bank targeted tests: **23/23 PASS**.
- Previous targeted regression pack của release: **34/34 PASS**.
- Python `compileall` backend: PASS.
- Migration `compileall`: PASS.
- Open edX connector `compileall`: PASS.
- Shell syntax release scripts: PASS.
- Frontend runtime contract: PASS.
- Frontend layout integrity: PASS.
- Production security closure source contract: PASS.
- Performance/worker reliability source contract: PASS.
- CI/E2E/container hardening source contract: PASS.
- npm public registry lockfile contract: PASS.
- Error-boundary contract: **0 blocker**, 75 warning broad best-effort branches được report để tiếp tục audit.

### Alembic smoke test

Bắt đầu tại `0059_v25_9_16_7_2_64_37`:

- upgrade 0059 → 0060 → 0061: PASS;
- head sau upgrade: `0061_v25_9_16_7_2_64_39`;
- legacy Question còn nguyên;
- legacy Quiz Blueprint còn nguyên;
- downgrade 0061 → 0060 → 0059: PASS;
- media table và type-quota columns được rollback đúng.

### Functional contracts đã test

- canonical validation cho 4 response type;
- AI Structured Output phân biệt Single/Multi;
- invalid Multi answer set bị reject trước DB;
- exact Single/Multi generation allocation;
- Quiz exact type quota;
- feasible/infeasible difficulty × type matrix;
- Open edX parser giữ 4 response type;
- unsupported regexp fail-closed;
- native Open edX OLX exporter cho 4 type;
- media MIME/checksum/SVG rejection;
- legacy Quiz type quota vẫn all-single;
- Celery broad failures không bị nuốt thành SUCCESS;
- RBAC legacy `CAMPUS_MANAGER` không cấp mới ở UI/schema/service/import.

## Baseline/full-suite comparison trong sandbox

Full backend suite không thể collection hoàn chỉnh trong runtime hiện tại vì các dependency production/test không đầy đủ. Khi chạy baseline `.16` và candidate `.18` cùng SQLite/runtime hiện tại, cả hai dừng tại cùng 4 collection errors trước test execution. Một lỗi đã kiểm trực tiếp là thiếu usable OpenAI runtime package trong pytest environment. Vì vậy lần chạy này **không được tính full-suite PASS**.

Các targeted/static suites phía trên là kết quả PASS thật và không dựa vào việc bỏ qua assertion product.

## Giới hạn môi trường còn lại

UAT gate có 3 WARN, không phải FAIL source:

1. `psycopg` không có trong sandbox nên gate backend production-dependency pytest bị skip.
2. `frontend/node_modules` không có nên chưa chạy production `npm ci + tsc + next build` trong lượt local cuối; review pack sinh lệnh bắt buộc chạy ở UAT.
3. Docker hoặc `.env.production` không có trong sandbox nên `docker compose ... config` phải chạy trên UAT/CI.

Ngoài ra `maintainability-contract-report.sh` cần `TOKEN` của AI Server UAT; sandbox không có token nên không thể gọi endpoint maintainability runtime.

## SonarQube

- Sonar-targeted source regression: PASS.
- Jenkins có SonarQube Analysis stage cho version `.18`.
- Không tuyên bố SonarQube server Quality Gate PASS trong sandbox vì không có Jenkins/Sonar credentials và server result.

## Điều kiện trước production sign-off

Trên CI/UAT phải chạy đầy đủ:

- PostgreSQL migration `alembic upgrade head`;
- frontend `npm ci`, `tsc --noEmit`, `next build`;
- backend tests với production requirements gồm `psycopg`;
- Docker Compose/K8s manifest validation;
- Jenkins SonarQube Analysis;
- smoke publish một câu có ảnh sang Open edX Library và verify static asset;
- smoke Quiz có ít nhất Single + Multi và một Quiz Blueprint exact quota.
