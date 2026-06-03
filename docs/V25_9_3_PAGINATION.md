# v25.9.3 - Pagination + Persistent Selection

## Added

- Paginated Question Bank via `GET /api/question-bank/page`.
- Paginated course chunks via `GET /api/courses/{course_id}/chunks/page`.
- Pagination controls for Question Bank, Review Queue, Generate chunk list, and Workflow chunk list.
- Page size selector: 10 / 20 / 50 / 100.
- Selection persists by ID when changing page/filter.
- Review queue shows visible vs hidden selected questions.
- Chunk selection keeps chunk objects in a local selected map so selected token totals stay correct across pages.

## Important UX rule

Pagination changes only the visible rows. It must not clear selected questions/chunks. Use `Clear selected` to clear selection explicitly.
