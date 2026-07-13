# Claude Code Review Handoff — v25.9.16.7.2.64.13

Review target: **Bank Workflow UX Completion**.

## Focus

- `backend/app/services/question_bank/import_export.py`
- New question page/export/import/release-preview routes in `question_bank_v2.py`
- `bank_question_import_task`
- `BankQuestionEnterpriseTable.tsx`
- `BankQuestionImportModal.tsx`
- `ChapterWorkspacePage.tsx`
- Hierarchy pages migrated to `EnterpriseDataTable`

## Verify

- No hierarchy change beyond Department → Subject → one Subject Version per term → Chapter → Question.
- Import cannot directly approve/publish.
- Preview token is user-owned and expires.
- Bulk scope distinguishes page selection from all filtered results.
- Release preview reads frozen release membership.
- No Assignment score write workflow returns.
