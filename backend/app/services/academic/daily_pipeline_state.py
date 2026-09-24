from dataclasses import dataclass
from typing import Iterable, Mapping


DAILY_PIPELINE_WINDOW = 4
MAX_STAGE_RETRY_ROUNDS = 3
STAGE_ORDER = (
    "ap_sync",
    "course_mapping",
    "account_enrollment",
    "score_update",
    "campus_reports",
    "ho_reports",
)
ACTIVE = {"queued", "running"}
SUCCESS = {"completed", "success"}
FAILED = {"failed", "cancelled", "canceled"}


@dataclass(frozen=True)
class StageBarrierDecision:
    ready: bool
    advance: bool
    exhausted: bool
    next_round: int | None
    retry_target_keys: tuple[str, ...]


def plan_stage_barrier(
    target_keys: Iterable[str],
    status_by_target: Mapping[str, str],
    *,
    current_round: int,
    max_retry_rounds: int = MAX_STAGE_RETRY_ROUNDS,
) -> StageBarrierDecision:
    targets = tuple(dict.fromkeys(str(value) for value in target_keys if str(value)))
    statuses = {key: str(status_by_target.get(key) or "").lower() for key in targets}
    if any(status not in SUCCESS | FAILED for status in statuses.values()):
        return StageBarrierDecision(False, False, False, None, ())

    failed = tuple(key for key in targets if statuses[key] in FAILED)
    if not failed:
        return StageBarrierDecision(True, True, False, None, ())
    if current_round >= max_retry_rounds:
        return StageBarrierDecision(True, False, True, None, failed)
    return StageBarrierDecision(True, False, False, current_round + 1, failed)


def select_global_dispatch_targets(
    target_keys: Iterable[str],
    status_by_target: Mapping[str, str],
    *,
    active_count: int,
    window: int = DAILY_PIPELINE_WINDOW,
) -> list[str]:
    limit = min(DAILY_PIPELINE_WINDOW, max(1, int(window)))
    slots = max(0, limit - max(0, int(active_count)))
    return [
        key
        for key in dict.fromkeys(str(value) for value in target_keys if str(value))
        if key not in status_by_target
    ][:slots]
