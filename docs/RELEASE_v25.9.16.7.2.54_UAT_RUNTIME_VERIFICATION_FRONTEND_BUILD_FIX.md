# v25.9.16.7.2.64.13 — RollNumber Identity Migration Assistant

Bản này tiếp tục từ `.53` và tập trung vào rủi ro identity sau khi chuẩn tạo tài khoản CMS/Open edX cho sinh viên đã chuyển sang RollNumber (`PH59017` → `ph59017`).

## Mục tiêu

- Phát hiện trước các mapping legacy đang dùng AP username/email cũ.
- Cho phép rà soát theo lớp, học kỳ, cơ sở, hệ, hoặc môn.
- Xuất report UAT để đối chiếu trước khi chạy Đồng bộ full CMS/Ghi danh CMS diện rộng.
- Không mutate dữ liệu trong endpoint/report này.

## API mới

```text
GET /api/academic/identity/rollnumber-migration
```

Query params:

```text
class_id
term_id
campus
branch
subject_id
status_filter=all|BLOCKERS|WARNINGS|OK|LEGACY_AP_USERNAME|MISSING_MAPPING|...
page
page_size
```

Response chính:

```text
status: READY | READY_WITH_WARNINGS | BLOCKED
severity_counts.blocker / warning / info
counts theo status
items[] gồm class, subject, term, AP username, RollNumber canonical username, openedx mapping hiện tại
next_actions[]
```

## Script mới

```bash
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
TERM_ID='<TERM_ID>' \
OUT_DIR=/tmp/rollnumber-identity-$(date +%Y%m%d-%H%M%S) \
./scripts/rollnumber-identity-migration-report.sh
```

Script xuất:

```text
rollnumber-identity-migration.json
ROLLNUMBER_IDENTITY_MIGRATION_SUMMARY.md
```

## An toàn dữ liệu

- Không xóa mapping.
- Không xóa snapshot.
- Không tạo user Open edX.
- Không enroll.
- Không gọi CMS để mutate.
- Không có migration mới.

Nếu muốn cleanup UAT dữ liệu sai vẫn dùng endpoint `.45` có confirm phrase riêng.

## Latest migration

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
