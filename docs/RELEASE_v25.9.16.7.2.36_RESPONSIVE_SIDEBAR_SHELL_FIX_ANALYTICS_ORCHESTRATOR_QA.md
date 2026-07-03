# v25.9.16.7.2.36 — Responsive Sidebar Shell Fix + Analytics Orchestrator QA

## Summary

Production UI polish release on top of `.35`. It fixes the responsive AppShell/sidebar regression shown in UAT screenshots: desktop/laptop narrow widths no longer turn the left rail into two columns, and tablet/mobile no longer let the sidebar expand beyond the viewport.

## Runtime impact

- Frontend CSS/AppShell only.
- No database migration.
- No backend contract change.
- Keeps `.35` post-ingest recalculate orchestrator unchanged.

## QA checklist

- Desktop/laptop: left sidebar remains one column.
- 1024px and below: nav becomes a bounded horizontal strip.
- 430px mobile: no page-level horizontal overflow; content starts below sidebar.
- `/analytics/learning` still shows roster/snapshot QA fields from `.34/.35`.
