# Claude Code Review Handoff — v25.9.16.7.2.64.13

Review target: **Academic AP Sync + External Assignment Workflow Split**.

## Focus

- `backend/app/services/academic/ap_sync.py`
- `backend/app/services/academic/assignment_external.py`
- `backend/app/api/routes/academic.py` AP sync routes and assignment score PUT deprecation
- `backend/app/services/business_rbac.py` removal of `academic.manage_assignment_scores`
- `frontend/app/student-management/classes/[classId]/page.tsx` removal of manual assignment workflow entry
- `frontend/context/AppContext.tsx`

## Expected properties

- AP sync route response shapes remain compatible.
- Existing Celery AP sync task behavior is unchanged.
- AI Server no longer grants UI/API permission to enter or edit Assignment score.
- Assignment score data is not deleted; old snapshots may still be displayed read-only.
- No schema migration.
