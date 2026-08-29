# AI Server / Open edX — Handoff Batch 35.2

- Version: `v25.9.16.7.2.64.16.5.7.2.6`.
- Baseline: Batch 35.1.
- Alembic head: `0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py`.
- No database migration.
- Deploy services: `backend`, `worker`, `frontend`.

## Canonical behavior

- Subject Management is term-level only.
- Database delivery and downstream operations remain Block-level.
- A term-level platform mutation expands to all delivery IDs for the subject.
- The nearest previous term is used only to prefill a consistent CMS/Udemy choice.
- No Udemy plan/progress/class/CMS mapping is copied between terms.
