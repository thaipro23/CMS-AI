# Claude Code Review Handoff — v25.9.16.7.2.51

## Baseline

Latest baseline: `v25.9.16.7.2.51 — Claude Code Review Readiness Pack`.

This version continues from:

- `.50` UAT Evidence Pack + Acceptance Report Export
- `.49` Analytics Pilot Acceptance UI + UAT Smoke Runner
- `.48` Campus RBAC Audit Hardening
- `.47` Bank Quiz Final Test Production QA
- `.46` Analytics SLA Dashboard + Job Observability
- `.45` UAT RollNumber Identity Cleanup
- `.44` RollNumber Identity Reconciliation QA
- `.43` Production Readiness Gate Repair
- `.42` Bank Table Production UX + Bulk Workflow QA
- `.40` CMS Student Username RollNumber Only
- `.37` Analytics Class Result Doctor
- `.35` Analytics Post-Ingest Recalculate Orchestrator

Latest migration remains:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## What Claude should review first

### 1. Identity safety

Student CMS/Open edX username must be RollNumber/student_code normalized lowercase.

Correct example:

```text
AP username: duongcvph59017@fpt.edu.vn
RollNumber: PH59017
CMS/Open edX username: ph59017
```

AP username/email should remain aliases only.

### 2. UAT cleanup guard

Destructive identity cleanup must only affect AI Server mapping/snapshot data and must require UAT env/explicit allow flag plus confirm phrase.

It must not delete:

- Open edX Django users
- AP students
- class roster
- course mapping
- tracking events
- raw analytics events

### 3. Analytics safety

Analytics HTTP endpoints must not scan raw `tracking.log` and must not recalculate synchronously in request path. Heavy work must go through Celery jobs.

### 4. RBAC/campus safety

Backend must enforce campus scope. Frontend hiding is not sufficient.

Limited campus manager should not be able to:

- create all-campus teacher report/export jobs;
- run all-campus bulk auto-map jobs;
- view/download jobs outside scope.

### 5. Bank workflow safety

`/bank/quiz` should not infer UI status from Vietnamese text. Final test rows default to `Tạo Final test`; Assignment/ASM rows default to `Không tạo` and do not block saving.

### 6. UX wording safety

UI should avoid hard conclusion wording:

```text
gian lận
cheating
vi phạm chắc chắn
treo máy chắc chắn
không học thật
```

Use soft labels such as:

```text
Dấu hiệu bất thường cần kiểm tra
Có khả năng treo máy
Chưa đủ dữ liệu
Cần giáo viên xác minh
```

## How to generate review artifacts

```bash
cd /opt/ai-server
OUT_DIR=/tmp/ai-server-claude-review-$(date +%Y%m%d-%H%M%S) \
./scripts/claude-code-review-pack.sh
```

Review these first:

```text
review-summary.json
CLAUDE_REVIEW_BRIEF.md
file-manifest.json
banned-wording-source.txt
dangerous-commands.txt
routes-raw-trackinglog.txt
```

## Expected review pack status

A clean artifact should have zero `FAIL`. `WARN` should be inspected manually, not ignored.
