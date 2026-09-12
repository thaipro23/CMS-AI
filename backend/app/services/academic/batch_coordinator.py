from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


ACTIVE_STATUSES = {'queued', 'running'}
SUCCESS_STATUSES = {'completed', 'success'}
FAILED_STATUSES = {'failed', 'canceled', 'cancelled'}


@dataclass(frozen=True)
class BatchDispatchPlan:
    window: int
    target_count: int
    known_count: int
    active_count: int
    completed_count: int
    failed_count: int
    terminal_count: int
    dispatch_class_ids: list[str]
    finished: bool


def plan_batch_dispatch(
    target_class_ids: Iterable[str],
    children: Iterable[Any],
    *,
    window: int,
) -> BatchDispatchPlan:
    """Plan the next bounded dispatch without mutating database or broker state."""
    targets = list(dict.fromkeys(str(value) for value in target_class_ids if str(value)))
    target_set = set(targets)
    status_by_class: dict[str, str] = {}
    for child in children:
        class_id = str(getattr(child, 'class_id', '') or '')
        if not class_id or class_id not in target_set or class_id in status_by_class:
            continue
        status_by_class[class_id] = str(getattr(child, 'status', '') or '').lower()

    active_count = sum(status in ACTIVE_STATUSES for status in status_by_class.values())
    completed_count = sum(status in SUCCESS_STATUSES for status in status_by_class.values())
    failed_count = sum(status in FAILED_STATUSES for status in status_by_class.values())
    terminal_count = completed_count + failed_count
    clean_window = max(1, min(20, int(window or 1)))
    slots = max(0, clean_window - active_count)
    undispatched = [class_id for class_id in targets if class_id not in status_by_class]
    dispatch_class_ids = undispatched[:slots]
    finished = bool(targets) and terminal_count == len(targets) and active_count == 0
    if not targets:
        finished = True
    return BatchDispatchPlan(
        window=clean_window,
        target_count=len(targets),
        known_count=len(status_by_class),
        active_count=active_count,
        completed_count=completed_count,
        failed_count=failed_count,
        terminal_count=terminal_count,
        dispatch_class_ids=dispatch_class_ids,
        finished=finished,
    )
