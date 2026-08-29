# Quiz Create Service Facade Hotfix — Batch 17

## Runtime error

```text
VersionedQuestionBankService.create_quiz_from_release() got an unexpected keyword argument 'course_chapter_mapping_id'
```

## Root cause

Batch 16 changed the canonical Quiz creation workflow to receive a persisted
`course_chapter_mapping_id`, but the public facade in
`backend/app/services/question_bank_service.py` still exposed the obsolete
signature based on `release_id`, `openedx_course_id` and `parent_node_id`.

Both the synchronous API route and `bank_quiz_create_task` correctly called the
new contract. Python therefore rejected the call before any Open edX operation
ran, leaving the job failed at the first execution step.

## Fix

The facade now mirrors `QuizCreationWorkflow.create_quiz_from_release()` and
forwards all fields used by the API route and Celery worker:

- `course_chapter_mapping_id`
- quiz/unit titles
- total and difficulty distribution
- family limit
- custom timer settings
- timeout/lock behavior
- native timed exam flag
- assessment type
- actor
- `expected_bank_release_id`

No API, database, RBAC or Open edX contract was changed.

## Operational note

Jobs that already failed will not resume automatically. After deploying this
hotfix, create the Quiz again from `/bank/quiz`; the new job will use the fixed
service facade.

No lint, typecheck, build or browser test was run per the user's current project
workflow preference.
