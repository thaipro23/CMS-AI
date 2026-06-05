# v25.9.14.5 — Test Report trung thực

## Đã chạy và PASS

```text
Python compile:
python -m compileall -q backend/app backend/alembic/versions openedx-connector-plugin/openedx_ai_connector
PASS

Backend tests:
pytest -q
37 passed, 2 skipped

Alembic graph:
alembic heads
0008_v25_9_14_5 (head)

Migration/service stable-family formula sample check:
PASS — công thức trong migration và runtime service trả cùng family ID.

Frontend typecheck:
npm run typecheck
PASS

Frontend production build:
NEXT_TELEMETRY_DISABLED=1 npm run build
PASS — 16/16 static pages, route /export build thành công.
```

Các test mới bao phủ:

- `concept_id` đã lưu là nguồn sự thật; hai concept ID khác nhau không bị gộp chỉ vì cùng title.
- Family cũ có suffix variant như `fam-...-easy-1/-2` được reconcile thành một family.
- Reconcile chạy lần hai không đổi `fam-v1-*` đã chuẩn hóa.
- Câu có nội dung normalize giống nhau chỉ giữ một canonical record trong plan.
- Planner không gọi LLM, giữ nguyên stable family trong một slot và dùng mọi câu duy nhất đúng một lần.
- Hard Guard từ chối khi cùng stable family bị tách sang nhiều slot.

## Chưa thể kiểm thử trong môi trường tạo bản này

- Chưa chạy migration `0008` trên PostgreSQL thật chứa dữ liệu production của người dùng.
- Chưa build Docker image vì môi trường tạo bản không có Docker daemon.
- Chưa gọi CMS/Open edX Tutor Ulmo.3 thật để publish Library, tạo Quiz hoặc insert Problem Bank.
- Chưa xác minh Family tag đã được backfill trên các component Open edX đã publish trước đây.

## Cảnh báo dependency

`npm ci` báo dependency hiện tại có `2 vulnerabilities (1 moderate, 1 high)`. Không chạy `npm audit fix --force` vì có thể nâng breaking dependency ngoài phạm vi bản sửa Stable Family. Cần đánh giá riêng trước khi production hardening.
