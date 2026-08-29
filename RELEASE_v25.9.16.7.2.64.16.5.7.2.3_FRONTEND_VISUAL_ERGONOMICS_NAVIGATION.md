# v25.9.16.7.2.64.16.5.7.2.3 — Frontend Visual Ergonomics & Navigation Hotfix

## Purpose

Close the visual and interaction regressions observed on the live UAT pages after the Full Frontend Design Contract release.

## Chapter workspace

- Removes the duplicated summary row containing total questions, approved questions and knowledge-family counts.
- Changes the primary labels to:
  - `Tạo câu hỏi (đã tạo/giới hạn)`;
  - `Duyệt câu hỏi (n câu chờ duyệt)`.
- Removes the `QA publish/rollback` panel and the now-redundant `Kiểm tra bộ đề` action.
- Keeps frozen Release preview available.
- Reduces question prompt, answer, metadata, badge and table emphasis to readable 400–600 weights.

## Topbar navigation

`PageChrome` and `PageHeader` now accept breadcrumb data. AppShell renders it as an accessible, clickable topbar path.

Bank hierarchy pages no longer use large back-link cards inside main content:

- Department → Subjects;
- Subject → Versions;
- Version → Chapters;
- Chapter workspace.

## Quiz and history

- Removes the duplicated `Ngân hàng đề` and `Lịch sử Quiz` header buttons from `/bank/quiz`.
- Forces Quiz and Final-test configuration panels to remain side by side on desktop and collapse only below 900px.
- Removes `Tạo Quiz trên CMS` from `/bank/history`.

## Student and teacher operations

- Makes `enterprise-content` the explicit vertical scroll owner for Student and Teacher Management.
- Restores touch/wheel vertical scrolling while retaining horizontal table scrolling.
- Prevents Teacher filters from becoming sticky/floating while the page scrolls.
- Removes teacher avatars from the report table and uses a text-only identity cell.
- Makes teacher notices, page actions and row actions participate in normal layout flow so controls cannot cover one another.

## Global visual ergonomics

A final imported stylesheet normalizes excessive legacy `750/800/900` font weights for operational content while preserving hierarchy through size, spacing, border and semantic status treatment.

## Compatibility

- Continues directly from `.64.16.5.7.2.2`.
- Preserves public npm registry lockfiles.
- Preserves CORS `X-Request-ID` support.
- No API, RBAC, Celery, Open edX or database behavior changes.
- No migration; Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
