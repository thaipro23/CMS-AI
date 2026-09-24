from app.services.academic.daily_pipeline_state import (
    DAILY_PIPELINE_WINDOW,
    MAX_STAGE_RETRY_ROUNDS,
    plan_stage_barrier,
    select_global_dispatch_targets,
)


def test_failed_target_waits_for_every_current_attempt_job_to_finish():
    decision = plan_stage_barrier(
        ["poly:term-1", "ptcd:term-2"],
        {"poly:term-1": "failed", "ptcd:term-2": "running"},
        current_round=0,
    )

    assert decision.ready is False
    assert decision.retry_target_keys == ()


def test_only_failed_targets_enter_next_round_and_round_three_exhausts():
    retry = plan_stage_barrier(
        ["poly:term-1", "ptcd:term-2"],
        {"poly:term-1": "completed", "ptcd:term-2": "failed"},
        current_round=0,
    )

    assert retry.next_round == 1
    assert retry.retry_target_keys == ("ptcd:term-2",)

    exhausted = plan_stage_barrier(
        ["ptcd:term-2"],
        {"ptcd:term-2": "failed"},
        current_round=MAX_STAGE_RETRY_ROUNDS,
    )

    assert exhausted.exhausted is True
    assert exhausted.advance is False


def test_global_dispatch_never_exceeds_four_slots():
    targets = [f"class-{index}" for index in range(10)]

    selected = select_global_dispatch_targets(
        targets,
        {"class-0": "running", "class-1": "queued"},
        active_count=2,
        window=DAILY_PIPELINE_WINDOW,
    )

    assert selected == ["class-2", "class-3"]


def test_all_successful_targets_advance_the_stage():
    decision = plan_stage_barrier(
        ["poly:term-1", "ptcd:term-2"],
        {"poly:term-1": "success", "ptcd:term-2": "completed"},
        current_round=2,
    )

    assert decision.ready is True
    assert decision.advance is True
    assert decision.exhausted is False
    assert decision.next_round is None
    assert decision.retry_target_keys == ()


def test_empty_stage_scope_is_ready_to_advance():
    decision = plan_stage_barrier([], {}, current_round=0)

    assert decision.ready is True
    assert decision.advance is True
    assert decision.exhausted is False


def test_unknown_status_keeps_the_stage_waiting():
    decision = plan_stage_barrier(
        ["poly:term-1"],
        {"poly:term-1": "unexpected"},
        current_round=0,
    )

    assert decision.ready is False
    assert decision.advance is False
    assert decision.exhausted is False


def test_duplicate_targets_are_only_retried_once_in_original_order():
    decision = plan_stage_barrier(
        ["poly:term-1", "ptcd:term-2", "poly:term-1"],
        {"poly:term-1": "failed", "ptcd:term-2": "cancelled"},
        current_round=1,
    )

    assert decision.next_round == 2
    assert decision.retry_target_keys == ("poly:term-1", "ptcd:term-2")


def test_dispatch_deduplicates_targets_and_skips_known_statuses():
    selected = select_global_dispatch_targets(
        ["class-1", "class-1", "class-2", "class-3"],
        {"class-2": "failed"},
        active_count=0,
    )

    assert selected == ["class-1", "class-3"]


def test_active_count_above_window_dispatches_nothing():
    selected = select_global_dispatch_targets(
        ["class-1", "class-2"],
        {},
        active_count=DAILY_PIPELINE_WINDOW + 1,
    )

    assert selected == []
