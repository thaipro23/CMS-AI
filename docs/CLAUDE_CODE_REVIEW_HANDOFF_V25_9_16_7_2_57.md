# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **AI Server / Open edX CMS v25.9.16.7.2.64.12 — Performance Load Hardening**.

## Review focus

1. `GET /api/health/performance-readiness` and `PerformanceReadinessService` must stay read-only and safe for request path.
2. The service must not scan raw tracking.log, enqueue jobs, recalculate analytics, call Open edX connector, run EXPLAIN ANALYZE, or mutate data.
3. Index contract checks should reflect critical model indexes for Bank, Academic, Jobs, and Analytics tables.
4. UI panel `/analytics/learning` should show actionable blocker/warning/action without hard violation wording.
5. Build/review gates from `.51-.53` must remain usable.

## Commands

```bash
OUT_DIR=/tmp/ai-server-claude-review-$(date +%Y%m%d-%H%M%S) \
EXPECTED_VERSION=25.9.16.7.2.64.12 \
./scripts/claude-code-review-pack.sh
```

```bash
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
./scripts/performance-readiness-report.sh
```

## Migration

Không migration mới. Latest remains:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
