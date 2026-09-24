from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


CLASS_SYNC_POLICY_VERSION = 'class-sync/v2'
CLASS_SYNC_KEY_PREFIX = 'class-sync:v2:'


def _optional_text(value: Any) -> str | None:
    clean = str(value or '').strip()
    return clean or None


def class_sync_contract(
    *,
    class_id: str,
    job_type: str,
    force: bool,
    limit: int,
    mode: str | None,
    auto_map_course: bool | None,
    sync_learning: bool | None,
    parent_job_id: str | None,
    origin: str,
    policy_version: str = CLASS_SYNC_POLICY_VERSION,
    attempt_no: int = 0,
    logical_target_key: str | None = None,
) -> dict[str, Any]:
    """Return the canonical business contract for one class-sync intent."""
    return {
        'class_id': str(class_id or '').strip(),
        'job_type': str(job_type or '').strip().lower(),
        'force': bool(force),
        'limit': int(limit),
        'mode': _optional_text(mode),
        'auto_map_course': (
            None if auto_map_course is None else bool(auto_map_course)
        ),
        'sync_learning': None if sync_learning is None else bool(sync_learning),
        'parent_job_id': _optional_text(parent_job_id),
        'origin': str(origin or '').strip().lower(),
        'policy_version': str(policy_version or '').strip(),
        'attempt_no': max(0, int(attempt_no)),
        'logical_target_key': _optional_text(logical_target_key),
    }


def class_sync_idempotency_key(**contract_values: Any) -> str:
    contract = class_sync_contract(**contract_values)
    payload = json.dumps(
        contract,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return f'{CLASS_SYNC_KEY_PREFIX}{hashlib.sha256(payload).hexdigest()}'


def class_sync_job_request_key(job: Any) -> str | None:
    """Read the v2 semantic key from a persisted job, including manual jobs."""
    durable_key = _optional_text(getattr(job, 'idempotency_key', None))
    if durable_key:
        return durable_key
    request = getattr(job, 'request_json', None)
    if isinstance(request, dict):
        return _optional_text(request.get('request_key'))
    return None


@dataclass(frozen=True)
class ActiveClassSyncDecision:
    reusable: Any | None
    blocker: Any | None


def choose_active_class_sync_job(
    active_jobs: Iterable[Any],
    *,
    requested_key: str,
) -> ActiveClassSyncDecision:
    """Choose exact reuse or fail closed on any different active contract."""
    exact = None
    blocker = None
    for job in active_jobs:
        if class_sync_job_request_key(job) == requested_key:
            exact = exact or job
        else:
            blocker = blocker or job
    if blocker is not None:
        return ActiveClassSyncDecision(reusable=None, blocker=blocker)
    return ActiveClassSyncDecision(reusable=exact, blocker=None)


class ClassSyncJobBlocked(RuntimeError):
    def __init__(self, blocker: Any):
        self.blocker = blocker
        self.blocking_job_id = str(getattr(blocker, 'id', '') or '')
        super().__init__(
            f'class sync is blocked by active job {self.blocking_job_id or "unknown"}'
        )
