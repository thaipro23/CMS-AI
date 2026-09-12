from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
import uuid

from app.core.config import settings


ORPHANED_JOB_CODE = 'CELERY_JOB_ORPHANED'


def enqueue_job_task(
    task: Any,
    job_id: str,
    *,
    queue: str,
    attempt: int = 1,
    countdown_seconds: int | None = None,
) -> dict[str, Any]:
    """Enqueue one durable job and return metadata that can be audited/retried."""
    task_name = str(getattr(task, 'name', None) or getattr(task, '__name__', 'unknown_task'))
    clean_attempt = max(1, int(attempt or 1))
    task_id = f'{task_name}:{job_id}:{clean_attempt}:{uuid.uuid4()}'
    kwargs = {'args': [job_id], 'task_id': task_id, 'queue': queue}
    if countdown_seconds is not None:
        kwargs['countdown'] = max(0, int(countdown_seconds))
    if bool(getattr(settings, 'task_always_eager', False)) and hasattr(task, 'apply'):
        result = task.apply(**kwargs)
    else:
        result = task.apply_async(**kwargs)
    metadata = {
        'task_name': task_name,
        'celery_task_id': str(getattr(result, 'id', None) or task_id),
        'queue': queue,
        'attempt': clean_attempt,
        'enqueued_at': datetime.utcnow().isoformat(),
    }
    if countdown_seconds is not None:
        metadata['countdown_seconds'] = max(0, int(countdown_seconds))
    return metadata


def persist_enqueue_metadata(job: Any, metadata: dict[str, Any]) -> None:
    result_json = dict(getattr(job, 'result_json', None) or {})
    history = list(result_json.get('enqueue_history') or [])
    history.append(dict(metadata))
    result_json['enqueue'] = dict(metadata)
    result_json['enqueue_history'] = history[-10:]
    job.result_json = result_json
    job.updated_at = datetime.utcnow()


def mark_enqueue_failed(job: Any, exc: Exception, *, now: datetime | None = None) -> None:
    failure_time = now or datetime.utcnow()
    message = 'Không đưa được tác vụ vào hàng đợi Celery/Redis. Hãy kiểm tra worker rồi chạy lại.'
    result_json = dict(getattr(job, 'result_json', None) or {})
    result_json.update({
        'ok': False,
        'code': 'CELERY_ENQUEUE_FAILED',
        'enqueue_error_type': exc.__class__.__name__,
    })
    job.status = 'failed'
    job.error_message = message
    job.progress_label = 'Đưa tác vụ vào hàng đợi thất bại'
    job.result_json = result_json
    job.finished_at = failure_time
    job.updated_at = failure_time


def reconcile_stale_rows(
    rows: Iterable[Any],
    *,
    now: datetime | None = None,
    queued_timeout_seconds: int,
    running_timeout_seconds: int,
    active_parent_ids: set[str] | None = None,
) -> list[Any]:
    """Fail active rows whose durable heartbeat is older than their lease."""
    check_time = now or datetime.utcnow()
    protected_ids = {str(value) for value in (active_parent_ids or set())}
    changed: list[Any] = []
    for job in rows:
        status = str(getattr(job, 'status', '') or '').lower()
        if status not in {'queued', 'running'} or str(getattr(job, 'id', '')) in protected_ids:
            continue
        reference = getattr(job, 'updated_at', None) or getattr(job, 'created_at', None)
        if reference is None:
            continue
        timeout_seconds = queued_timeout_seconds if status == 'queued' and getattr(job, 'started_at', None) is None else running_timeout_seconds
        if (check_time - reference).total_seconds() <= max(1, int(timeout_seconds)):
            continue
        result_json = dict(getattr(job, 'result_json', None) or {})
        result_json.update({
            'code': ORPHANED_JOB_CODE,
            'orphaned_at': check_time.isoformat(),
            'previous_status': status,
        })
        job.status = 'failed'
        job.error_message = 'Worker Celery đã ngắt hoặc không cập nhật tiến độ trong thời gian cho phép. Có thể chạy lại tác vụ an toàn.'
        job.progress_label = 'Tác vụ bị gián đoạn do worker'
        job.result_json = result_json
        job.finished_at = check_time
        job.updated_at = check_time
        changed.append(job)
    return changed
