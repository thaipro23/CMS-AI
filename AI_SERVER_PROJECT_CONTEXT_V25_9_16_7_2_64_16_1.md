# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.1

## Baseline canonical

```text
v25.9.16.7.2.64.16.1 — Enterprise Visual Foundation + Dense Table Contract + Review UX
zip: ai-server-openedx-v25.9.16.7.2.64.16.1-enterprise-visual-foundation-review-ux.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_1
```

Bản này tiếp tục trực tiếp từ `.64.16`; không dùng baseline cũ khi phát triển tiếp.

## UI contract mới

```text
Sidebar: dark cố định
Topbar/content: light cố định
Theme switcher: removed
Desktop sidebar: 64/220px
Mobile: accessible drawer
```

`EnterpriseDataTable` có column kind và priority để giảm chiều rộng cột số, ẩn cột ít giá trị trước khi horizontal scroll và giữ sticky/URL/server-side contract.

## Question review

- Review preview-first bằng drawer bên phải.
- Bảng chỉ ưu tiên preview câu hỏi, status, difficulty, quality và action gọn.
- Full A/B/C/D, correct answer, explanation, evidence, concept/family nằm trong drawer.
- Bulk bar chỉ xuất hiện khi selection > 0.
- Keyboard J/K/A/R/E/Escape.

## RBAC UI

- Trang `/users` theo user/assignment/scope, không dùng role card wall.
- SYSTEM_ADMIN toàn hệ thống; DEPARTMENT_HEAD/SUBJECT_OWNER/QUESTION_REVIEWER kế thừa xuống node con; CAMPUS_OWNER theo cơ sở; TEACHER_ASSIGNED theo AP.
- Frontend ẩn route/action không có quyền; backend tiếp tục enforce entity scope.

## Production

```env
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
```

Không có diagnostics/test UI production. Không Bootstrap, Metronic, jQuery hoặc major dependency upgrade.

## Database và nghiệp vụ

- Không migration mới; latest `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Không reset DB/xóa volume/sửa tay Alembic.
- Bank: Department → Subject → một Subject Version cuối/term → Chapter → Question.
- Release/Quiz là workflow đầu ra.
- Assignment score write vẫn externalized.

## Verification

```text
Backend compileall PASS
TypeScript PASS
Release tests 11 passed
Selected regression 35 passed
Next build 29/29 + standalone PASS
UX gate READY 24/24
Security static READY 20/20
Maintainability 0 blocker, 6 inherited warnings
```

## Roadmap tiếp theo

- `.64.16.2`: Bank/Quiz workflow visual completion.
- `.64.16.3`: Student/Teacher/Analytics detailed UX.
- `.64.16.4`: Ops/Catalog/Settings/RBAC completion.
- `.64.16.5`: responsive/accessibility/cross-browser acceptance hotfix.
- `.65`: production rollout.
