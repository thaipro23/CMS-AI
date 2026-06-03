# v24.5 - Question Control UI + Delete Question

## UI change

Question Bank and Teacher Review no longer show three separate boxes.

New layout:

1. Main question box
   - Question text
   - 4 answers A/B/C/D
   - Correct answer highlighted green

2. Control box
   - Status
   - Actions

Meta/source/chapter/library fields remain hidden from the outer list. They are still stored in the database and used by filtering, export, publish and source-node randomization.

## Delete question

Added individual delete for non-published questions.

Endpoint:

```http
DELETE /api/question-bank/{question_id}?actor=teacher
```

Permission:

```txt
edit_questions
```

Rules:

- pending_review / approved / rejected / draft_error can be deleted.
- published questions are blocked from delete because they may already exist in Open edX.
- Delete removes local AI Server data for the question, review logs, versions and duplicate embedding row.

Frontend:

- `QuestionTable` has optional `onDelete` prop.
- Delete button appears only when `onDelete` exists, user can edit, and question is not published.
- User must confirm before deleting.
