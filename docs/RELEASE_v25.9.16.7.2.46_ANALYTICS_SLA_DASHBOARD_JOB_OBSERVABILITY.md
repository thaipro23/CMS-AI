# v25.9.16.7.2.50 — Bank Quiz Final Test Production QA

## Summary

Adds a read-only SLA dashboard for the analytics pipeline:

```text
tracking.log ingest → post-ingest recalculate → behavior snapshot → UI
```

The endpoint uses materialized operational data only. It never scans raw tracking logs, never enqueues jobs, and never recalculates snapshots inside the request.

## New endpoint

```text
GET /api/analytics/ops/sla?limit=20
```

## New frontend panel

```text
/analytics/learning → SLA vận hành analytics
```

## New env controls

```env
ANALYTICS_SLA_INGEST_TARGET_SECONDS=300
ANALYTICS_SLA_SNAPSHOT_TARGET_SECONDS=3600
ANALYTICS_SLA_MAX_QUEUED_JOBS=50
ANALYTICS_SLA_MAX_FAILED_JOBS_LAST_HOUR=0
ANALYTICS_SLA_CLASS_GAP_LIMIT=20
```

## Migration

No migration. Latest remains:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
