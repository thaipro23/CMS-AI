# UX/UI Context v25.9.16.7.2.34

## Baseline

Continues from `v25.9.16.7.2.33 — Class Actions Toolbar + Learning Roster Fallback`.

## UX intent

The `.34` UI change is intentionally small and production-focused: operators should immediately understand whether `/analytics/learning` is missing student data because the AP roster is empty or because behavior snapshots have not been materialized yet.

## `/analytics/learning` result view

The result summary strip now includes:

```text
Tổng sinh viên
Snapshot nhận định
Thiếu snapshot
Có dấu hiệu học thật
Có khả năng treo máy
Dấu hiệu bất thường cần kiểm tra
Chưa đủ dữ liệu
Chưa thấy bất thường rõ
```

Rules:

- `Tổng sinh viên` follows AP roster when `class_id` is selected.
- `Snapshot nhận định` displays `snapshot_count/roster_count`.
- `Thiếu snapshot` displays `missing_snapshot_count`.
- Missing behavior snapshot rows remain `Chưa đủ dữ liệu`.
- Do not use wording such as `gian lận`, `cheating`, or definitive violation language.

## Class detail action toolbar

The `.33` toolbar fix remains:

- equal button width;
- horizontal/wrapping layout on desktop/laptop;
- responsive two-column/one-column behavior on mobile;
- no forced single vertical column on desktop.

## No fake data

All new indicators are explicit backend payload fields. The frontend may only fall back to safe arithmetic for display when the backend is temporarily older, and must not invent status labels or conclusions.
