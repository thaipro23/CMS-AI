from __future__ import annotations

from typing import Any


MIN_REPLICA_DELAY_SECONDS = 10
MAX_REPLICA_DELAY_SECONDS = 900


def bounded_replica_delay_seconds(value: int | None) -> int:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = MIN_REPLICA_DELAY_SECONDS
    return max(MIN_REPLICA_DELAY_SECONDS, min(seconds, MAX_REPLICA_DELAY_SECONDS))


def should_enqueue_learning_followup(*, requested: bool, enabled: bool, flow_status: str | None) -> bool:
    return bool(requested and enabled and str(flow_status or '') == 'completed')


def build_learning_sync_followup(
    *,
    requested_by: str | None,
    class_id: str,
    force: bool,
    limit: int,
    requester_context: dict[str, Any] | None,
    parent_job_id: str | None,
    delay_seconds: int,
) -> dict[str, Any]:
    """Build the durable second pass run after enrollment reaches replicas."""

    clean_limit = max(1, min(20_000, int(limit or 500)))
    return {
        'job_type': 'learning_sync',
        'status': 'queued',
        'class_id': str(class_id),
        'requested_by': requested_by or 'academic-sync-worker',
        'force': bool(force),
        'limit': clean_limit,
        'mode': None,
        'countdown': bounded_replica_delay_seconds(delay_seconds),
        'request_json': {
            'force': bool(force),
            'limit': clean_limit,
            'parent_job_type': 'full_cms_sync',
            'parent_job_id': parent_job_id,
            'delayed_after_enrollment': True,
            'requester_context': requester_context or {},
            'approved_class_id': str(class_id),
        },
    }
