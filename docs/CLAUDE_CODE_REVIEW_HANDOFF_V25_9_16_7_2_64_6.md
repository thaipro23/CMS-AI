# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **Question Bank Quiz Creation/Auto-map Workflow Split**.

## Focus files

- `backend/app/services/question_bank/quiz_creation.py`
- `backend/app/services/question_bank_service.py`
- `backend/app/services/maintainability_contract.py`
- `backend/app/tests/test_v25_9_16_7_2_64_10_question_bank_quiz_creation_automap_workflow_split.py`

## Expected properties

- Public service method names and route/API behavior remain compatible.
- Open edX quiz creation semantics are not rewritten.
- Native Problem Bank insertion and custom timer force-save semantics remain unchanged.
- Auto-map preview/apply still respects `quiz`, `final_test`, `assignment`, and `skip` actions.
- No Alembic migration is introduced.
