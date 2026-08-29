# Claude Code Review Handoff — v25.9.16.7.2.64.13

Review target: **Teacher Report Cache/Training Report Workflow Split**.

## Focus files

- `backend/app/services/academic/teacher_report.py`
- `backend/app/services/academic_service.py`
- `backend/app/api/routes/academic.py`
- `backend/app/worker.py`
- `backend/app/services/maintainability_contract.py`

## Expected properties

- `/api/academic/training/teachers` response shape unchanged.
- Teacher report list, export, lite-fast fallback, cached report and cache rebuild use same semantics as before.
- `AcademicService` delegates to `AcademicTeacherReportWorkflowService`.
- Student Ops access boundary remains preserved.
- No migration.
