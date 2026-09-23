from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.json_safe import json_safe_value
from app.models.academic import AcademicBulkOperationJob


Publisher = Callable[..., Any]


def scheduled_parent_key(
    prefix: str,
    *,
    run_date_vn: str,
    term_id: str,
    branch: str,
) -> str:
    return ':'.join((
        str(prefix or '').strip().lower(),
        str(run_date_vn or '').strip(),
        str(term_id or '').strip(),
        str(branch or '').strip().lower(),
    ))


def create_or_load_scheduled_parent(
    db: Session,
    *,
    idempotency_key: str,
    values: dict[str, Any],
) -> tuple[AcademicBulkOperationJob, bool]:
    existing = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.idempotency_key == idempotency_key,
    ).one_or_none()
    if existing is not None:
        return existing, False

    parent = AcademicBulkOperationJob(
        **values,
        idempotency_key=idempotency_key,
    )
    db.add(parent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.idempotency_key == idempotency_key,
        ).one_or_none()
        if existing is None:
            raise
        return existing, False
    db.refresh(parent)
    return parent, True


class ContinuationPublishError(RuntimeError):
    def __init__(self, parent_id: str, original: Exception):
        self.parent_id = parent_id
        self.original = original
        super().__init__(
            f'could not publish continuation for parent {parent_id}: {original}'
        )


def _task_id(value: Any) -> str:
    return str(getattr(value, 'id', None) or value or '')


def publish_parent_continuation(
    db: Session,
    parent: AcademicBulkOperationJob,
    *,
    publisher: Publisher,
    task_name: str,
    args: list[Any],
    queue: str,
    countdown: int = 0,
    now: datetime | None = None,
    max_attempts: int = 5,
) -> str:
    current_time = now or datetime.utcnow()
    state = dict(parent.result_json or {})
    previous = (
        dict(state.get('continuation') or {})
        if isinstance(state.get('continuation'), dict)
        else {}
    )
    previous_status = str(previous.get('status') or '')
    attempts = (
        1
        if previous_status in {'', 'confirmed'}
        else int(previous.get('attempt_count') or 0) + 1
    )
    if attempts > max(1, int(max_attempts)):
        parent.status = 'failed'
        parent.error_message = 'Continuation dispatch exceeded its retry limit.'
        parent.finished_at = current_time
        state['continuation'] = {
            **previous,
            'status': 'failed',
            'attempt_count': attempts - 1,
            'failed_at': current_time.isoformat(),
            'last_error': parent.error_message,
        }
        parent.result_json = json_safe_value(state)
        parent.updated_at = current_time
        db.add(parent)
        db.commit()
        raise ContinuationPublishError(
            str(parent.id),
            RuntimeError(parent.error_message),
        )

    continuation = {
        'status': 'dispatch_pending',
        'attempt_count': attempts,
        'due_at': (
            current_time
            + timedelta(seconds=max(0, int(countdown)) + 90)
        ).isoformat(),
        'task_name': str(task_name),
        'args': list(args),
        'queue': str(queue),
        'countdown': max(0, int(countdown)),
        'intent_created_at': current_time.isoformat(),
        'last_error': None,
        'last_error_class': None,
    }
    state['continuation'] = continuation
    parent.result_json = json_safe_value(state)
    parent.updated_at = current_time
    db.add(parent)
    db.commit()

    try:
        result = publisher(
            task_name=task_name,
            args=list(args),
            queue=queue,
            countdown=max(0, int(countdown)),
        )
    except Exception as exc:
        state = dict(parent.result_json or {})
        continuation = dict(state.get('continuation') or {})
        retry_delay = min(300, 15 * (2 ** max(0, attempts - 1)))
        continuation.update({
            'status': 'dispatch_pending',
            'due_at': (current_time + timedelta(seconds=retry_delay)).isoformat(),
            'last_error': str(exc)[:2000],
            'last_error_class': exc.__class__.__name__,
            'last_error_at': current_time.isoformat(),
        })
        state['continuation'] = continuation
        parent.result_json = json_safe_value(state)
        parent.updated_at = current_time
        db.add(parent)
        db.commit()
        raise ContinuationPublishError(str(parent.id), exc) from exc

    state = dict(parent.result_json or {})
    continuation = dict(state.get('continuation') or {})
    continuation.update({
        'status': 'dispatched',
        'task_id': _task_id(result),
        'dispatched_at': current_time.isoformat(),
    })
    state['continuation'] = continuation
    parent.result_json = json_safe_value(state)
    parent.updated_at = current_time
    db.add(parent)
    db.commit()
    return continuation['task_id']


def confirm_parent_continuation(
    db: Session,
    parent: AcademicBulkOperationJob,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.utcnow()
    state = dict(parent.result_json or {})
    continuation = (
        dict(state.get('continuation') or {})
        if isinstance(state.get('continuation'), dict)
        else {}
    )
    continuation.update({
        'status': 'confirmed',
        'confirmed_at': current_time.isoformat(),
        'last_error': None,
        'last_error_class': None,
    })
    state['continuation'] = continuation
    parent.result_json = json_safe_value(state)
    parent.updated_at = current_time
    db.add(parent)
    db.commit()


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def recover_due_parent_continuations(
    db: Session,
    *,
    publisher: Publisher,
    job_types: Iterable[str],
    now: datetime | None = None,
    max_attempts: int = 5,
    max_runtime_seconds: int = 6 * 60 * 60,
    limit: int = 100,
) -> dict[str, Any]:
    current_time = now or datetime.utcnow()
    jobs = (
        db.query(AcademicBulkOperationJob)
        .filter(
            AcademicBulkOperationJob.job_type.in_(set(job_types)),
            AcademicBulkOperationJob.status.in_(['queued', 'running']),
        )
        .order_by(AcademicBulkOperationJob.created_at.asc())
        .limit(max(1, int(limit)))
        .all()
    )
    due: list[AcademicBulkOperationJob] = []
    for parent in jobs:
        state = parent.result_json if isinstance(parent.result_json, dict) else {}
        continuation = (
            state.get('continuation')
            if isinstance(state.get('continuation'), dict)
            else {}
        )
        if str(continuation.get('status') or '') not in {
            'dispatch_pending',
            'dispatched',
        }:
            continue
        due_at = _parse_time(continuation.get('due_at'))
        if due_at is None or due_at <= current_time:
            due.append(parent)

    result: dict[str, Any] = {
        'scanned': len(due),
        'republished': 0,
        'failed': 0,
        'errors': [],
    }
    for parent in due:
        state = dict(parent.result_json or {})
        continuation = dict(state.get('continuation') or {})
        created_at = _parse_time(parent.created_at)
        attempts = int(continuation.get('attempt_count') or 0)
        if (
            attempts >= max(1, int(max_attempts))
            or (
                created_at is not None
                and (current_time - created_at).total_seconds()
                > max(1, int(max_runtime_seconds))
            )
        ):
            parent.status = 'failed'
            parent.error_message = 'Scheduled continuation recovery limit exceeded.'
            parent.finished_at = current_time
            continuation.update({
                'status': 'failed',
                'failed_at': current_time.isoformat(),
                'last_error': parent.error_message,
            })
            state['continuation'] = continuation
            parent.result_json = json_safe_value(state)
            parent.updated_at = current_time
            db.add(parent)
            db.commit()
            result['failed'] += 1
            continue
        try:
            publish_parent_continuation(
                db,
                parent,
                publisher=publisher,
                task_name=str(continuation.get('task_name') or ''),
                args=list(continuation.get('args') or []),
                queue=str(continuation.get('queue') or 'sync-bulk'),
                countdown=int(continuation.get('countdown') or 0),
                now=current_time,
                max_attempts=max_attempts,
            )
            result['republished'] += 1
        except ContinuationPublishError as exc:
            result['errors'].append({
                'parent_job_id': str(parent.id),
                'error': str(exc.original)[:500],
                'error_class': exc.original.__class__.__name__,
            })
    return result
