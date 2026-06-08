# v25.9.15.0 Test Report

## Scope

Bản này thêm kiến trúc `Question Bank First` có version:

- Department / Subject / Chapter
- Question Bank Version
- Material Version
- Concept Version
- Bank Question Family
- Bank Release
- Release Questions
- Open edX Course Mapping
- Course Chapter Mapping
- Quiz Blueprint
- Course Quiz Instance

Nguyên tắc chính: **1 Bank Release = 1 Open edX Library**.

## Checks completed in artifact environment

```text
Python compileall backend/app backend/alembic: PASS
Zip integrity: PASS
```

## Tests added

```text
backend/app/tests/test_versioned_question_bank.py
```

Coverage:

- Release creates deterministic Open edX Library key per subject/chapter/version.
- Release includes only approved/published questions in the selected bank version.
- Course mapping points Open edX course to subject without making course the owner of questions.

## Tests not executed here

`pytest` could not be executed in this artifact environment because the Python environment does not have project dependencies installed:

```text
ModuleNotFoundError: No module named 'sqlalchemy'
```

Docker is also unavailable in the artifact environment:

```text
docker: command not found
```

Run the real tests inside your backend container after build:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend \
  pytest app/tests/test_versioned_question_bank.py app/tests/test_stable_family_planner.py -q -vv
```

Run migration check:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend \
  alembic upgrade head
```

## Honest production status

This build creates the persistent data model, API and guided UI for versioned question banks. It does **not** yet migrate every existing course-first question automatically into a subject/chapter bank; that needs a deliberate migration/import workflow because the user must choose Department/Subject/Chapter and version policy.

Open edX native ItemBank connector from v25.9.14.6.1 is preserved. A full end-to-end test still needs to be run on your Tutor Ulmo.3 server.
