# UX context v25.9.16.7.2.14

The two pages have different aggregation semantics:

- `/student-management`: grouped by subject. KPIs are for the subject rows currently displayed on the page unless backend later adds a full summary.
- `/teacher-management`: grouped by teacher. Class/student counters are teacher-class workload counts. A co-taught class is counted once per teacher.

This release makes that visible in UI to avoid false interpretation that AP sync is missing data.
