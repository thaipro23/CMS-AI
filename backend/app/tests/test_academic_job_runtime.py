from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.academic.job_runtime import (
    enqueue_job_task,
    persist_enqueue_metadata,
    reconcile_stale_rows,
)


NOW = datetime(2026, 9, 12, 12, 0, 0)


def _job(*, job_id: str = 'job-1', status: str, age_seconds: int, started: bool = True):
    return SimpleNamespace(
        id=job_id,
        status=status,
        created_at=NOW - timedelta(seconds=age_seconds),
        started_at=(NOW - timedelta(seconds=age_seconds)) if started else None,
        updated_at=NOW - timedelta(seconds=age_seconds),
        finished_at=None,
        progress_label='Đang xử lý',
        error_message=None,
        result_json={'kept': True},
    )


class _Task:
    name = 'academic_test_task'

    def __init__(self):
        self.calls: list[dict] = []

    def apply_async(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=kwargs['task_id'])


def test_running_job_past_lease_is_marked_failed_with_recovery_code():
    job = _job(status='running', age_seconds=601)

    changed = reconcile_stale_rows(
        [job],
        now=NOW,
        queued_timeout_seconds=900,
        running_timeout_seconds=600,
    )

    assert changed == [job]
    assert job.status == 'failed'
    assert job.finished_at == NOW
    assert job.result_json == {
        'kept': True,
        'code': 'CELERY_JOB_ORPHANED',
        'orphaned_at': NOW.isoformat(),
        'previous_status': 'running',
    }
    assert 'worker' in job.error_message.lower()


def test_never_started_queued_job_uses_queued_lease():
    job = _job(status='queued', age_seconds=901, started=False)

    reconcile_stale_rows(
        [job],
        now=NOW,
        queued_timeout_seconds=900,
        running_timeout_seconds=600,
    )

    assert job.status == 'failed'
    assert job.result_json['previous_status'] == 'queued'


def test_active_parent_is_protected_from_short_bulk_lease():
    job = _job(job_id='parent-1', status='running', age_seconds=601)

    changed = reconcile_stale_rows(
        [job],
        now=NOW,
        queued_timeout_seconds=900,
        running_timeout_seconds=600,
        active_parent_ids={'parent-1'},
    )

    assert changed == []
    assert job.status == 'running'


def test_enqueue_metadata_records_real_task_id_queue_and_attempt():
    task = _Task()

    metadata = enqueue_job_task(task, 'job-1', queue='sync', attempt=3)

    assert metadata['task_name'] == 'academic_test_task'
    assert metadata['queue'] == 'sync'
    assert metadata['attempt'] == 3
    assert metadata['celery_task_id'].startswith('academic_test_task:job-1:3:')
    assert task.calls == [{
        'args': ['job-1'],
        'task_id': metadata['celery_task_id'],
        'queue': 'sync',
    }]


def test_continuation_enqueue_applies_bounded_countdown():
    task = _Task()

    metadata = enqueue_job_task(
        task,
        'parent-1',
        queue='sync',
        attempt=2,
        countdown_seconds=10,
    )

    assert metadata['countdown_seconds'] == 10
    assert task.calls[0]['countdown'] == 10


def test_persist_enqueue_metadata_keeps_last_ten_attempts():
    job = _job(status='queued', age_seconds=0, started=False)
    job.result_json = {'enqueue_history': [{'attempt': value} for value in range(1, 11)]}

    persist_enqueue_metadata(job, {'attempt': 11})

    assert [item['attempt'] for item in job.result_json['enqueue_history']] == list(range(2, 12))
    assert job.result_json['enqueue'] == {'attempt': 11}
