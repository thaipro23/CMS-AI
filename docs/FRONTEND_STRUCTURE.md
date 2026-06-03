# Frontend Structure - v8

The v8 frontend is split into dedicated routes instead of keeping all features in one page.

## Pages

| Route | Purpose |
|---|---|
| `/dashboard` | Overview statistics: questions, jobs, costs, sync, quota |
| `/sync` | Sync course content from Open edX and browse chunks |
| `/generate` | Choose manual or course-chunks mode, estimate cost, generate questions |
| `/review` | Teacher Review Queue, edit, approve/reject, bulk approve |
| `/question-bank` | Full bank with filter/search/sort and manual status correction |
| `/export` | Convert approved questions to Open edX OLX/XML |
| `/jobs` | Monitor generation jobs |
| `/settings` | Demo RBAC and shared settings |

## Main directories

```text
frontend/
  app/
    dashboard/page.tsx
    sync/page.tsx
    generate/page.tsx
    review/page.tsx
    question-bank/page.tsx
    export/page.tsx
    jobs/page.tsx
    settings/page.tsx
  components/
    layout/AppShell.tsx
    questions/QuestionTable.tsx
    questions/QuestionFilters.tsx
    questions/QuestionEditPanel.tsx
    ui/MetricCard.tsx
    ui/StatPanel.tsx
    ui/StatusBadge.tsx
  context/AppContext.tsx
  lib/api.ts
  types/index.ts
```

## Design principles

1. **One route = one user task.** Generate, review, export, sync, dashboard and settings are separate.
2. **API calls are centralized.** Pages call `frontend/lib/api.ts`, not raw endpoints everywhere.
3. **Shared types are centralized.** Question, Job, Chunk, Analytics and RBAC types are in `frontend/types`.
4. **Reusable components.** Question table/edit/filter components are reused by review and question bank pages.
5. **RBAC ready.** Role and user are stored in `AppContext`; production can replace this with Open edX SSO mapping.
6. **Easy extension.** Future pages such as Chatbot, Prompt Policy, Model Gateway, Cost Governance and Local Model Settings can be added without touching unrelated pages.
