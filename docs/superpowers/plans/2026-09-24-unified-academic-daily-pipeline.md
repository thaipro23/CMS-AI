# Unified 01:00 Academic Daily Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the independent 03:00 and 05:00 academic schedules with one durable 01:00 Vietnam-time pipeline that processes Poly and PTCD through AP sync, mapping, provisioning, score refresh, canonical assessment projection, campus exports, and branch-specific HO exports with a global four-job limit and three end-of-stage retries.

**Architecture:** One `AcademicBulkOperationJob` is the root for each Vietnam run date. A new coordinator freezes every `(branch, term_id)` scope, owns all dispatch decisions, persists attempt state before publishing Celery work, and advances only after the cross-branch stage barrier succeeds. Existing AP, class-sync, snapshot, and Excel workers remain execution adapters; pure state-planning code decides global capacity and retry transitions, while one shared assessment selector prevents structural Open edX nodes from becoming UI or workbook columns.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Celery/Redis, PostgreSQL, pytest, OpenPyXL, existing Open edX Connector client.

**Spec:** `docs/superpowers/specs/2026-09-22-academic-job-report-quiz-hardening-design.md`

## Global Constraints

- Celery Beat publishes exactly one root at `01:00` in `Asia/Ho_Chi_Minh`; the legacy 03:00 and 05:00 entries publish nothing.
- The ordered stages are `ap_sync`, `course_mapping`, `account_enrollment`, `score_update`, `campus_reports`, and `ho_reports`.
- Poly and PTCD are both mandatory. No report stage starts until every score target in both branches succeeds.
- At most four daily-pipeline jobs may be `queued` or `running` across both branches combined.
- Each logical target has one initial attempt and at most three end-of-stage retry attempts; successful targets never run again.
- A retry starts only after every job in the current attempt is terminal.
- Mutation retries use the same logical mutation intent, reconcile current state, and apply only missing effects.
- Campus and HO snapshots fail closed on an explicit class, teacher, or campus branch mismatch in either direction.
- A null legacy `teacher.branch` inherits `class.branch`; an explicit different teacher branch is invalid.
- Campus files complete before branch-specific `HO-Poly` or `HO-PTCD` work starts.
- Scheduled/bulk work and continuations use `sync-bulk`; workbook workers use `exports`.
- Every database state transition is committed before Celery publication, and duplicate continuation delivery must not create another attempt.
- Existing manual AP, class sync, score refresh, and report APIs retain their current task names and behavior.
- Raw Open edX learning snapshots remain intact, but student lists, teacher summaries, and Excel exports expose only canonical numbered Quiz columns plus at most one Final test column; structural `Demo`/`Phần` nodes are excluded.

## Review Focus

- A worker dies after an attempt row commits but before Celery confirmation: recovery must republish the same attempt without incrementing its retry round.
- One mandatory branch has no active term or campus: the root must fail before AP dispatch and must not silently run only the other branch.
- A PTCD class is assigned to an explicit Poly teacher, or the inverse: campus snapshot creation must fail; a null teacher branch must inherit the class branch.
- A mixed Open edX payload contains valid quizzes plus repeated `Demo`/`Phần` rows under different usage keys: only canonical Quiz/Final-test columns reach the UI and workbooks, while raw snapshot evidence remains intact.
- A campus export succeeds while another exhausts retry round three: the successful campus is not repeated, HO is not created, and the previous successful daily artifacts remain untouched.

---

### Task 1: Pure stage barrier and global dispatch planner

**Files:**
- Create: `backend/app/services/academic/daily_pipeline_state.py`
- Create: `backend/app/tests/test_academic_daily_stage_coordinator.py`

**Interfaces:**
- Produces: `DAILY_PIPELINE_WINDOW: int`, `MAX_STAGE_RETRY_ROUNDS: int`, `STAGE_ORDER: tuple[str, ...]`.
- Produces: `StageBarrierDecision(ready, advance, exhausted, next_round, retry_target_keys)`.
- Produces: `plan_stage_barrier(target_keys, status_by_target, current_round, max_retry_rounds=3) -> StageBarrierDecision`.
- Produces: `select_global_dispatch_targets(target_keys, status_by_target, active_count, window=4) -> list[str]`.

- [ ] **Step 1: Write failing barrier and capacity tests**

```python
from app.services.academic.daily_pipeline_state import (
    DAILY_PIPELINE_WINDOW,
    MAX_STAGE_RETRY_ROUNDS,
    plan_stage_barrier,
    select_global_dispatch_targets,
)


def test_failed_target_waits_for_every_current_attempt_job_to_finish():
    decision = plan_stage_barrier(
        ['poly:term-1', 'ptcd:term-2'],
        {'poly:term-1': 'failed', 'ptcd:term-2': 'running'},
        current_round=0,
    )
    assert decision.ready is False
    assert decision.retry_target_keys == ()


def test_only_failed_targets_enter_next_round_and_round_three_exhausts():
    retry = plan_stage_barrier(
        ['poly:term-1', 'ptcd:term-2'],
        {'poly:term-1': 'completed', 'ptcd:term-2': 'failed'},
        current_round=0,
    )
    assert retry.next_round == 1
    assert retry.retry_target_keys == ('ptcd:term-2',)

    exhausted = plan_stage_barrier(
        ['ptcd:term-2'],
        {'ptcd:term-2': 'failed'},
        current_round=MAX_STAGE_RETRY_ROUNDS,
    )
    assert exhausted.exhausted is True
    assert exhausted.advance is False


def test_global_dispatch_never_exceeds_four_slots():
    targets = [f'class-{index}' for index in range(10)]
    selected = select_global_dispatch_targets(
        targets,
        {'class-0': 'running', 'class-1': 'queued'},
        active_count=2,
        window=DAILY_PIPELINE_WINDOW,
    )
    assert selected == ['class-2', 'class-3']
```

- [ ] **Step 2: Run the new tests and verify import failure**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_stage_coordinator.py -q`

Expected: FAIL because `daily_pipeline_state` does not exist.

- [ ] **Step 3: Implement the pure state model**

```python
from dataclasses import dataclass
from typing import Iterable, Mapping


DAILY_PIPELINE_WINDOW = 4
MAX_STAGE_RETRY_ROUNDS = 3
STAGE_ORDER = (
    'ap_sync',
    'course_mapping',
    'account_enrollment',
    'score_update',
    'campus_reports',
    'ho_reports',
)
ACTIVE = {'queued', 'running'}
SUCCESS = {'completed', 'success'}
FAILED = {'failed', 'cancelled', 'canceled'}


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
    statuses = {key: str(status_by_target.get(key) or '').lower() for key in targets}
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
        key for key in dict.fromkeys(str(value) for value in target_keys if str(value))
        if key not in status_by_target
    ][:slots]
```

- [ ] **Step 4: Add tests for all-success, explicit empty scope, unknown status, duplicate targets, and active counts above four**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_stage_coordinator.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/academic/daily_pipeline_state.py backend/app/tests/test_academic_daily_stage_coordinator.py
git commit -m "feat(academic): add daily stage retry planner"
```

### Task 2: Durable hierarchy and per-attempt idempotency

**Files:**
- Create: `backend/alembic/versions/0067_academic_daily_pipeline_v2.py`
- Modify: `backend/app/models/academic.py`
- Modify: `backend/app/services/academic/ap_sync.py`
- Modify: `backend/app/services/academic/job_identity.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_schema.py`
- Modify: `backend/app/tests/test_academic_job_semantic_identity.py`
- Modify: `backend/app/tests/test_current_alembic_head_contract.py`
- Modify: `backend/app/api/routes/health.py`
- Modify: `scripts/question-bank-data-health.py`
- Modify: `scripts/uat-build-gate.sh`
- Modify: `scripts/claude-code-review-pack.sh`
- Modify: `deploy/k8s/jobs/kustomization.yaml`

**Interfaces:**
- Produces: nullable indexed `AcademicBulkOperationJob.parent_job_id`.
- Produces: nullable unique indexed `AcademicSyncRun.idempotency_key`.
- Produces: nullable indexed `AcademicTeacherReportJob.parent_job_id` and nullable unique indexed `idempotency_key`.
- Changes: `AcademicAPSyncWorkflowService.enqueue_sync_from_ap_job(payload, *, user, idempotency_key=None, run_metadata=None)` reuses only the exact run key.
- Changes: `class_sync_contract(*, class_id, job_type, force, limit, mode, auto_map_course, sync_learning, parent_job_id, origin, policy_version=CLASS_SYNC_POLICY_VERSION, attempt_no=0, logical_target_key=None)` includes scheduled attempt identity while defaults preserve manual identity.

- [ ] **Step 1: Write failing model, migration, AP reuse, and class-attempt identity tests**

```python
def test_daily_pipeline_attempt_columns_are_nullable_and_indexed():
    assert AcademicBulkOperationJob.__table__.c.parent_job_id.nullable is True
    assert AcademicSyncRun.__table__.c.idempotency_key.unique is True
    assert AcademicTeacherReportJob.__table__.c.parent_job_id.nullable is True
    assert AcademicTeacherReportJob.__table__.c.idempotency_key.unique is True


def test_class_attempt_changes_job_key_but_preserves_logical_target():
    base = dict(
        class_id='class-1', job_type='learning_sync', force=True, limit=5000,
        mode=None, auto_map_course=False, sync_learning=True,
        parent_job_id='scope-1', origin='scheduled',
        logical_target_key='score:poly:term-1:class-1',
    )
    first = class_sync_idempotency_key(**base, attempt_no=0)
    retry = class_sync_idempotency_key(**base, attempt_no=1)
    assert first != retry
    assert first.startswith('class-sync:v2:')
    assert retry.startswith('class-sync:v2:')
```

- [ ] **Step 2: Run focused tests and verify missing columns/signatures**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_schema.py app/tests/test_academic_job_semantic_identity.py app/tests/test_current_alembic_head_contract.py -q`

Expected: FAIL on the new columns, migration head, and keyword arguments.

- [ ] **Step 3: Add migration `0067` after `0066_academic_pipeline_hardening`**

The upgrade creates these additive columns and indexes:

```python
op.add_column('academic_bulk_operation_jobs', sa.Column('parent_job_id', sa.String(), nullable=True))
op.create_index('ix_academic_bulk_operation_jobs_parent_job_id', 'academic_bulk_operation_jobs', ['parent_job_id'])
op.add_column('academic_sync_runs', sa.Column('idempotency_key', sa.String(length=255), nullable=True))
op.create_index('ix_academic_sync_runs_idempotency_key', 'academic_sync_runs', ['idempotency_key'], unique=True)
op.add_column('academic_teacher_report_jobs', sa.Column('parent_job_id', sa.String(), nullable=True))
op.add_column('academic_teacher_report_jobs', sa.Column('idempotency_key', sa.String(length=255), nullable=True))
op.create_index('ix_academic_teacher_report_jobs_parent_job_id', 'academic_teacher_report_jobs', ['parent_job_id'])
op.create_index('ix_academic_teacher_report_jobs_idempotency_key', 'academic_teacher_report_jobs', ['idempotency_key'], unique=True)
```

The downgrade drops the new indexes before their columns. Use the migration helpers already used by `0066` so repeated UAT upgrades remain safe.

- [ ] **Step 4: Implement exact AP and class-attempt identity**

In `enqueue_sync_from_ap_job`, acquire the existing scope lock, load `AcademicSyncRun.idempotency_key == idempotency_key`, and return it before checking foreign active work. New runs persist both the key and `run_metadata` inside `counters_json['daily_pipeline']`.

Extend the class contract with these normalized fields:

```python
'attempt_no': max(0, int(attempt_no)),
'logical_target_key': _optional_text(logical_target_key),
```

Manual callers omit both arguments and retain `attempt_no=0` and `logical_target_key=None`.

- [ ] **Step 5: Run schema and semantic regression tests**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_schema.py app/tests/test_academic_job_semantic_identity.py app/tests/test_academic_job_batch_schema.py app/tests/test_current_alembic_head_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0067_academic_daily_pipeline_v2.py backend/app/models/academic.py backend/app/services/academic/ap_sync.py backend/app/services/academic/job_identity.py backend/app/tests/test_academic_daily_pipeline_schema.py backend/app/tests/test_academic_job_semantic_identity.py backend/app/tests/test_current_alembic_head_contract.py backend/app/api/routes/health.py scripts/question-bank-data-health.py scripts/uat-build-gate.sh scripts/claude-code-review-pack.sh deploy/k8s/jobs/kustomization.yaml
git commit -m "feat(academic): persist daily attempt identity"
```

### Task 3: Single 01:00 root and frozen Poly/PTCD scopes

**Files:**
- Create: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/services/academic/student_management_runtime.py`
- Modify: `backend/app/services/academic/daily_teacher_report_runtime.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_schedule.py`
- Modify: `backend/app/tests/test_academic_scheduled_parent_recovery.py`
- Modify: `backend/app/tests/test_academic_split_course_score_scheduler_contract.py`
- Modify: `backend/app/tests/test_daily_teacher_report_pipeline_contract.py`

**Interfaces:**
- Produces: `DAILY_ROOT_JOB_TYPE = 'academic_daily_pipeline_v2'`.
- Produces: `DAILY_START_TASK = 'academic_daily_pipeline_start_task'` and `DAILY_ROOT_TASK = 'academic_daily_pipeline_task'`.
- Produces: `daily_root_key(run_date_vn) -> 'academic-daily:v2:{date}'`.
- Produces: `discover_daily_scopes(db) -> list[dict[str, object]]` sorted by branch then term ID.
- Produces: `ensure_scope_parents(db, root, scopes) -> dict[str, AcademicBulkOperationJob]` using the stable `:provision` and `:score-report` keys from the spec.
- Produces: `start_daily_academic_pipeline(celery_app, *, now=None) -> dict[str, object]`.
- Produces: `run_daily_academic_pipeline(celery_app, root_job_id) -> dict[str, object]`.

- [ ] **Step 1: Write failing schedule, duplicate-root, and mandatory-branch tests**

```python
def test_beat_has_one_0100_pipeline_and_no_legacy_daily_publishers(celery_app):
    schedule = celery_app.conf.beat_schedule
    assert schedule['academic-daily-pipeline-01-vn']['task'] == 'academic_daily_pipeline_start_task'
    assert 'academic-ap-sync-and-auto-map-03-vn' not in schedule
    assert 'academic-score-sync-all-students' not in schedule


def test_duplicate_start_reuses_one_root(monkeypatch, session_factory):
    monkeypatch.setattr(runtime, 'SessionLocal', session_factory)
    first = runtime.start_daily_academic_pipeline(FakeCelery(), now=VN_NOW)
    second = runtime.start_daily_academic_pipeline(FakeCelery(), now=VN_NOW)
    assert first['root_job_id'] == second['root_job_id']


def test_missing_ptcd_scope_fails_before_ap_dispatch(monkeypatch, session_factory):
    seed_active_term(branch='poly')
    result = runtime.start_daily_academic_pipeline(FakeCelery(), now=VN_NOW)
    assert result['ok'] is False
    assert result['code'] == 'mandatory_branch_scope_missing'
    assert FakeCelery.sent == []
```

- [ ] **Step 2: Run the schedule tests and verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_schedule.py app/tests/test_academic_scheduled_parent_recovery.py app/tests/test_academic_split_course_score_scheduler_contract.py app/tests/test_daily_teacher_report_pipeline_contract.py -q`

Expected: FAIL because the root runtime/task/schedule do not exist and legacy schedules remain.

- [ ] **Step 3: Implement root creation and frozen scope discovery**

The root `request_json` must contain this stable contract before any child is published:

```python
{
    'scheduled': True,
    'schedule_time': '01:00',
    'timezone': 'Asia/Ho_Chi_Minh',
    'run_date_vn': run_date_vn,
    'policy_version': 'academic-daily/v2',
    'required_branches': ['poly', 'ptcd'],
    'scopes': scopes,
}
```

The initial `result_json` is:

```python
{
    'schema_version': 'academic-daily-state.v2',
    'phase': 'ap_sync',
    'stage_round': 0,
    'stage_target_keys': [scope['scope_key'] for scope in scopes],
    'attempts_by_stage': {},
    'artifacts': {},
}
```

Every active term must have a normalized branch in `{'poly', 'ptcd'}`, at least one active campus belonging to that branch, and a deterministic class/campus scope. Missing either mandatory branch creates one failed root with no child publication.

For each frozen scope, create or load two child bulk rows with `parent_job_id=root.id`:

```text
academic-daily:v2:{run_date_vn}:{term_id}:{branch}:provision
academic-daily:v2:{run_date_vn}:{term_id}:{branch}:score-report
```

These rows own class-sync and report attempt jobs; the root remains the only dispatcher.

- [ ] **Step 4: Register the root tasks and remove old Beat entries**

Register the two new tasks on `sync-bulk`, add:

```python
beat_schedule['academic-daily-pipeline-01-vn'] = {
    'task': DAILY_START_TASK,
    'schedule': crontab(hour=1, minute=0),
}
```

Remove the 03:00 registration in `student_management_runtime.py` and the 05:00 entry in `worker.py`. Keep legacy task handlers registered for manual/backward-compatible calls, but do not schedule them.

- [ ] **Step 5: Persist and recover the root continuation**

Use `create_or_load_scheduled_parent`, `publish_parent_continuation`, and `confirm_parent_continuation`. Add `DAILY_ROOT_JOB_TYPE` to the recovery scanner with a 24-hour maximum root runtime. Duplicate Beat or continuation deliveries reuse the same root and continuation intent.

- [ ] **Step 6: Run focused schedule/recovery tests**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_schedule.py app/tests/test_academic_scheduled_parent_recovery.py app/tests/test_academic_split_course_score_scheduler_contract.py app/tests/test_daily_teacher_report_pipeline_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/academic/daily_academic_pipeline.py backend/app/worker.py backend/app/services/academic/student_management_runtime.py backend/app/services/academic/daily_teacher_report_runtime.py backend/app/tests/test_academic_daily_pipeline_schedule.py backend/app/tests/test_academic_scheduled_parent_recovery.py backend/app/tests/test_academic_split_course_score_scheduler_contract.py backend/app/tests/test_daily_teacher_report_pipeline_contract.py
git commit -m "feat(academic): schedule one daily pipeline at 01:00"
```

### Task 4: AP and map-only stages with end-of-stage retries

**Files:**
- Modify: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/services/academic/student_management_runtime.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_ap_mapping.py`
- Modify: `backend/app/tests/test_academic_auto_map_batch_coordinator.py`

**Interfaces:**
- Produces: `enqueue_ap_stage_attempt(db, root, scope, round_no) -> AcademicSyncRun`.
- Produces: `ensure_mapping_attempt(db, root, scope, round_no) -> AcademicBulkOperationJob`.
- Changes: `academic_subject_auto_map_all_sync_task` accepts `request_json['operation'] == 'map_only'` and completes without class-sync fan-out.
- Consumes: `plan_stage_barrier` and `select_global_dispatch_targets` from Task 1.

- [ ] **Step 1: Write failing AP barrier and retry tests**

```python
def test_ap_failure_is_not_retried_until_other_branch_is_terminal():
    root = seed_root_with_ap_attempts(poly='failed', ptcd='running', round_no=0)
    result = runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert result['status'] == 'waiting_stage'
    assert count_ap_attempts(root.id, branch='poly') == 1


def test_ap_retry_uses_new_run_id_and_same_logical_target():
    root = seed_root_with_ap_attempts(poly='failed', ptcd='completed', round_no=0)
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    attempts = ap_attempts(root.id, branch='poly')
    assert [item.counters_json['daily_pipeline']['round'] for item in attempts] == [0, 1]
    assert len({item.id for item in attempts}) == 2


def test_mapping_waits_for_every_ap_scope_to_succeed():
    root = seed_root_with_ap_attempts(poly='completed', ptcd='failed', round_no=3)
    result = runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert result['code'] == 'stage_retry_exhausted'
    assert count_mapping_jobs(root.id) == 0
```

- [ ] **Step 2: Run focused tests and verify current behavior fails**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_ap_mapping.py app/tests/test_academic_auto_map_batch_coordinator.py -q`

Expected: FAIL because AP and mapping are still coupled by the legacy 03:00 parent.

- [ ] **Step 3: Implement AP attempt dispatch under the global window**

Use attempt keys:

```text
academic-daily:v2:{run_date_vn}:{term_id}:{branch}:ap:attempt:{round_no}
```

Pass that key to `enqueue_sync_from_ap_job`. Store root ID, scope key, stage name, round, and source run ID in both root state and `AcademicSyncRun.counters_json['daily_pipeline']`. Do not create round `n + 1` until all round `n` AP targets are terminal.

- [ ] **Step 4: Add map-only behavior**

For a `map_only` job, call `auto_map_subject_courses_for_snapshot`, persist the returned counts and frozen class IDs, and finish immediately:

```python
if request_json.get('operation') == 'map_only':
    mandatory_failed = bool(
        int(state.get('subject_failed') or 0)
        or int(state.get('scope_blocked_class_count') or 0)
    )
    state['phase'] = 'finished'
    job.status = 'failed' if mandatory_failed else 'completed'
    job.result_json = json_safe_value(state)
    job.finished_at = datetime.utcnow()
    db.add(job)
    db.commit()
    return json_safe_value({'ok': not mandatory_failed, **state})
```

The coordinator creates only failed mapping targets in retry rounds 1–3. It copies the successful frozen scope into root state and does not call `_finish_scheduled_auto_map_parent` for v2 roots.

- [ ] **Step 5: Add regression tests proving no provisioning child exists in `map_only` mode**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_ap_mapping.py app/tests/test_academic_auto_map_batch_coordinator.py app/tests/test_academic_scheduled_scope.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/academic/daily_academic_pipeline.py backend/app/worker.py backend/app/services/academic/student_management_runtime.py backend/app/tests/test_academic_daily_pipeline_ap_mapping.py backend/app/tests/test_academic_auto_map_batch_coordinator.py
git commit -m "feat(academic): separate AP and course mapping stages"
```

### Task 5: Globally bounded provisioning and score stages

**Files:**
- Modify: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/services/academic/job_identity.py`
- Modify: `backend/app/services/academic/sync_enrollment.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_provision_score.py`
- Modify: `backend/app/tests/test_academic_job_truthful_outcome.py`

**Interfaces:**
- Produces: `ensure_class_attempt_job(db, *, scope_parent, class_id, stage, round_no, request) -> AcademicClassSyncJob`.
- Produces: `class_provisioning_gap(class_id) -> dict[str, object]` on the enrollment workflow service.
- Changes: scheduled v2 class jobs set `stage_managed_retries=True`, `logical_target_key`, `attempt_no`, and `mutation_intent_key` in `request_json`.
- Consumes: `full_cms_sync(auto_map_course=False, sync_learning=False, force=False)` for provisioning and `learning_sync` for scores.

- [ ] **Step 1: Write failing global-window, separated-stage, and retry tests**

```python
def test_provisioning_across_two_branches_has_only_four_active_children():
    root = seed_mapping_complete_root(class_count_by_branch={'poly': 5, 'ptcd': 5})
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert count_active_daily_class_jobs(root.id) == 4
    assert set(active_daily_job_branches(root.id)) == {'poly', 'ptcd'}


def test_score_stage_does_not_start_until_all_provisioning_retries_succeed():
    root = seed_provision_attempts(poly='completed', ptcd='failed', round_no=2)
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert count_score_jobs(root.id) == 0
    assert latest_stage_round(root.id) == 3


def test_scheduled_learning_failure_is_terminal_for_stage_coordinator():
    job = seed_learning_job(stage_managed_retries=True)
    run_class_task_with_transient_failure(job.id)
    assert reload(job).status == 'failed'
    assert celery_retry_was_called() is False


def test_foreign_manual_class_job_blocks_but_is_never_adopted():
    manual = seed_active_manual_class_job(class_id='class-poly-1')
    root = seed_mapping_complete_root(class_count_by_branch={'poly': 1, 'ptcd': 1})
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert manual.parent_job_id is None
    assert scheduled_attempt_ids(root.id, class_id='class-poly-1') == []
    assert count_active_daily_class_jobs(root.id) <= 4


def test_provision_retry_reconciles_and_submits_only_missing_effects():
    seed_student_state('student-1', account='matched', enrollment='enrolled')
    seed_student_state('student-2', account='missing', enrollment='unknown')
    result = run_provision_retry(class_id='class-poly-1', round_no=1)
    assert result['reconciled_student_ids'] == ['student-1', 'student-2']
    assert connector_resolve_usernames() == ['student-2']
    assert connector_enroll_usernames() == ['student-2']
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_provision_score.py app/tests/test_academic_job_truthful_outcome.py -q`

Expected: FAIL because branch parents currently own separate windows and scheduled learning jobs retry internally.

- [ ] **Step 3: Implement attempt-specific class jobs**

Provisioning request fields are exact:

```python
{
    'scheduled': True,
    'stage_managed_retries': True,
    'daily_root_job_id': root.id,
    'scheduled_parent_job_id': scope_parent.id,
    'scheduled_scope_hash': scope['scope_hash'],
    'logical_target_key': f"account_enrollment:{scope['scope_key']}:{class_id}",
    'mutation_intent_key': f"academic-daily:v2:{run_date}:account_enrollment:{scope['scope_key']}:{class_id}",
    'attempt_no': round_no,
    'auto_map_course': False,
    'sync_learning': False,
}
```

Create a new child row for each retry round. Never call `_restart_academic_class_sync_child_job` for v2 daily work. Before a provisioning retry, `class_provisioning_gap` reads current user mappings and enrollment snapshots; `full_cms_sync(force=False)` resolves or enrolls only missing effects.

- [ ] **Step 4: Make scheduled score retries stage-owned**

In `academic_class_sync_task`, compute:

```python
stage_managed = bool(request_json.get('stage_managed_retries'))
retry_allowed = (
    not stage_managed
    and automatic_retry_allowed(job.job_type, transient=transient_failure)
)
```

Manual `learning_sync` retains its bounded Celery retry. Daily score children become terminal failures so the coordinator retries them only after the whole score attempt is terminal.

- [ ] **Step 5: Implement cross-branch provision and score barriers**

The root counts all active v2 class children across every scope before selecting new targets. It advances from provisioning only when every class succeeds, then creates fresh `learning_sync` attempts. Retry exhaustion records `failed_stage`, `failed_scope_keys`, `failed_target_keys`, and final child IDs and leaves report job counts at zero.

- [ ] **Step 6: Run class-sync and pipeline regressions**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_provision_score.py app/tests/test_academic_job_truthful_outcome.py app/tests/test_academic_job_semantic_identity.py app/tests/test_academic_job_atomic_claim.py app/tests/test_academic_auto_map_batch_coordinator.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/academic/daily_academic_pipeline.py backend/app/worker.py backend/app/services/academic/job_identity.py backend/app/services/academic/sync_enrollment.py backend/app/tests/test_academic_daily_pipeline_provision_score.py backend/app/tests/test_academic_job_truthful_outcome.py
git commit -m "feat(academic): coordinate provision and score retries globally"
```

### Task 6: Remove structural Open edX nodes from assessment columns

**Files:**
- Create: `backend/app/services/academic/assessment_components.py`
- Modify: `backend/app/services/academic_service.py`
- Create: `backend/app/tests/test_academic_assessment_component_contract.py`
- Create: `frontend/lib/academicAssessments.ts`
- Modify: `frontend/types/index.ts`
- Modify: `frontend/app/student-management/classes/[classId]/page.tsx`
- Modify: `frontend/app/teacher-management/TeacherManagementPlatformPage.tsx`
- Create: `e2e/tests/student-grade-column-hygiene.spec.ts`

**Interfaces:**
- Produces: `canonical_assessment_identity(item: Mapping[str, Any]) -> str | None`.
- Produces: `canonical_assessment_components(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]`.
- Produces: frontend `CanonicalAssessmentColumn` and `canonicalAssessmentColumns(scores: AcademicLearningComponentScore[]) -> CanonicalAssessmentColumn[]` using the same quiz/final identity contract.
- Changes: raw `AcademicStudentLearningSnapshot.raw_json` stays unchanged; only API/report presentation payloads are filtered.
- Consumes: explicit positive `quiz_number`, human-facing `Quiz N`/`Learning Check N`/`LC N`, or explicit/normalized `Final test` identity. Storage-key digits alone never create a quiz.

- [ ] **Step 1: Write failing backend behavior tests for the reported junk columns**

```python
from app.services.academic.assessment_components import canonical_assessment_components


def test_structural_demo_and_part_rows_never_become_assessment_columns():
    rows = [
        {'key': 'quiz-real', 'name': 'Quiz 1', 'quiz_number': 1, 'percent': 80},
        {'key': 'demo-a', 'name': 'Demo', 'category': 'subsection', 'percent': 100},
        {'key': 'demo-b', 'name': 'Demo', 'category': 'subsection', 'percent': 90},
        {'key': 'demo-lesson-1', 'name': 'Demo bài 1', 'percent': 100},
        {'key': 'part-1-a', 'name': 'Phần 1', 'percent': 100},
        {'key': 'part-1-b', 'name': 'Phần 1', 'percent': 80},
        {'key': 'final-a', 'name': 'Final test', 'assessment_type': 'final_test', 'percent': 70},
    ]
    result = canonical_assessment_components(rows)
    assert [(row['key'], row['name']) for row in result] == [
        ('quiz:1', 'Quiz 1'),
        ('final_test', 'Final test'),
    ]


def test_quiz_duplicates_collapse_by_number_and_prefer_real_score():
    rows = [
        {'key': 'outline-q2', 'name': 'Quiz 2', 'quiz_number': 2, 'planned': True, 'percent': None},
        {'key': 'grade-q2', 'name': 'Learning Check 2', 'quiz_number': 2, 'planned': False, 'percent': 95},
    ]
    result = canonical_assessment_components(rows)
    assert len(result) == 1
    assert result[0]['key'] == 'quiz:2'
    assert result[0]['name'] == 'Quiz 2'
    assert result[0]['percent'] == 95
    assert result[0]['planned'] is False


def test_storage_key_number_does_not_create_phantom_quiz():
    rows = [{'key': 'block@quiz-14-random', 'name': 'Demo', 'category': 'problem', 'percent': 100}]
    assert canonical_assessment_components(rows) == []
```

- [ ] **Step 2: Prove the current parser reproduces the defect**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_assessment_component_contract.py -q`

Expected: FAIL because no canonical assessment boundary exists and usage-key-distinct `Demo`/`Phần 1` rows survive into summaries.

- [ ] **Step 3: Implement one canonical backend selector without mutating raw snapshots**

Use human-facing fields only when inferring identity:

```python
QUIZ_LABEL = re.compile(r'\b(?:quiz|learning\s*check|lc)\s*#?\s*(\d{1,3})\b', re.I)


def canonical_assessment_identity(item: Mapping[str, Any]) -> str | None:
    explicit = _positive_int(item.get('quiz_number'))
    labels = ' '.join(str(item.get(key) or '') for key in ('name', 'label', 'display_name', 'title'))
    match = QUIZ_LABEL.search(labels)
    number = explicit or (_positive_int(match.group(1)) if match else None)
    if number:
        return f'quiz:{number}'
    assessment_type = str(item.get('assessment_type') or '').strip().lower()
    normalized_label = _normalize_label(labels)
    if assessment_type == 'final_test' or normalized_label == 'final test':
        return 'final_test'
    return None
```

`canonical_assessment_components` groups by that identity, canonicalizes names to `Quiz N` or `Final test`, prefers non-planned rows with actual `percent`/`earned`, merges dates from the remaining duplicate, and sorts numbered quizzes before Final test. It never infers quiz order from generic list position or digits in `key`/`usage_key`.

- [ ] **Step 4: Apply the selector at every presentation boundary**

Keep `_component_scores_from_snapshot()` unchanged for policy evaluation and diagnostics. Apply the selector:

```python
raw_components = self._enrich_component_scores_for_class(
    self._component_scores_from_snapshot(learning), cls, quiz_schedule_by_number,
)
display_components = canonical_assessment_components(raw_components)
```

Return `display_components` as `learning_component_scores`. In `_component_summary_from_snapshots`, canonicalize each learner's normalized rows before bucketing, then run the existing deadline enrichment once on the aggregated result so class summaries, teacher summaries, campus workbooks, and HO inputs use `quiz:{number}`/`final_test` keys without adding per-learner schedule queries. Do not rewrite `snapshot.raw_json`, total grade, progress, or the component list passed to `TrainingPolicyService.evaluate_student`.

Preserve `assessment_type` from connector rows in `_normalize_component_score_item`, and add `assessment_type?: string | null` to `AcademicLearningComponentScore`; this makes explicit Final-test identity survive the backend/frontend boundary instead of relying only on its display label.

- [ ] **Step 5: Add a frontend fail-safe and browser regression**

Move column identity/building to `frontend/lib/academicAssessments.ts`. `canonicalAssessmentColumns` must reject any score without a canonical quiz/final identity, even if an old cache or mixed-version backend returns it. Use it in the student list and teacher management table.

The Playwright fixture returns `Quiz 1`, two `Demo` keys, sixteen `Phần 1` keys, and one `Final test` in `component_summaries`. Assert:

```typescript
await expect(page.getByRole('columnheader', { name: 'Quiz 1', exact: true })).toHaveCount(1)
await expect(page.getByRole('columnheader', { name: 'Final test', exact: true })).toHaveCount(1)
await expect(page.getByRole('columnheader', { name: /^Demo/ })).toHaveCount(0)
await expect(page.getByRole('columnheader', { name: /^Phần [1-4]$/ })).toHaveCount(0)
```

- [ ] **Step 6: Run assessment and UI regressions**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_assessment_component_contract.py app/tests/test_training_policy_service.py app/tests/test_teacher_management_all_cms_regression.py -q`

Run: `cd frontend && npm run typecheck`

Run: `cd e2e && npx playwright test tests/student-grade-column-hygiene.spec.ts --reporter=line`

Expected: PASS; the reported payload yields only `Quiz 1` and `Final test`, while scoring-policy tests remain unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/academic/assessment_components.py backend/app/services/academic_service.py backend/app/tests/test_academic_assessment_component_contract.py frontend/lib/academicAssessments.ts frontend/types/index.ts 'frontend/app/student-management/classes/[classId]/page.tsx' frontend/app/teacher-management/TeacherManagementPlatformPage.tsx e2e/tests/student-grade-column-hygiene.spec.ts
git commit -m "fix(academic): remove structural nodes from grade columns"
```

### Task 7: Symmetric Poly/PTCD report isolation

**Files:**
- Modify: `backend/app/services/academic/teacher_report.py`
- Modify: `backend/app/services/academic/report_snapshot.py`
- Modify: `backend/app/services/academic/daily_teacher_report_runtime.py`
- Create: `backend/app/tests/test_academic_teacher_report_branch_isolation.py`
- Modify: `backend/app/tests/test_academic_teacher_report_snapshots.py`

**Interfaces:**
- Produces: `TeacherReportBranchScopeError`.
- Changes: `training_teacher_report(user, *, term_id=None, branch=None, campus=None, search=None, learning_status=None, learning_platform=None, teacher_id=None, class_id=None, page=1, page_size=50, include_all=False, include_students=False, include_classes=False, use_cache=True, student_row_limit=20000, allowed_class_ids=None, enforce_branch_integrity=False)` performs a scheduled-snapshot preflight when true.
- Changes: `validate_campus_report(report, *, campus, branch)` validates class and effective teacher branch.
- Produces: `validate_report_branch(report, *, branch) -> dict[str, int]`.

- [ ] **Step 1: Write failing two-way branch tests**

```python
@pytest.mark.parametrize(
    ('scheduled_branch', 'foreign_branch'),
    [('poly', 'ptcd'), ('ptcd', 'poly')],
)
def test_snapshot_rejects_explicit_opposite_teacher_branch(scheduled_branch, foreign_branch):
    report = report_payload(branch=scheduled_branch, teacher_branch=foreign_branch)
    with pytest.raises(ReportSnapshotError, match='teacher branch'):
        validate_campus_report(report, campus='hn', branch=scheduled_branch)


@pytest.mark.parametrize('branch', ['poly', 'ptcd'])
def test_null_teacher_branch_inherits_class_branch(branch):
    report = report_payload(branch=branch, teacher_branch=None)
    counts = validate_campus_report(report, campus='hn', branch=branch)
    assert counts['teacher_count'] == 1


def test_scheduled_query_detects_cross_branch_assignment_instead_of_hiding_it(db):
    seed_assignment(class_branch='ptcd', teacher_branch='poly')
    with pytest.raises(TeacherReportBranchScopeError):
        AcademicService(db).training_teacher_report(
            scheduler_user(), term_id='term-ptcd', branch='ptcd', campus='hn',
            include_all=True, include_students=True, use_cache=False,
            allowed_class_ids={'class-ptcd'}, enforce_branch_integrity=True,
        )
```

- [ ] **Step 2: Run branch tests and verify current leakage behavior**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_teacher_report_branch_isolation.py app/tests/test_academic_teacher_report_snapshots.py -q`

Expected: FAIL because teacher branch is not part of the scheduled snapshot contract.

- [ ] **Step 3: Add scheduled-query preflight**

Before the full report query, detect explicit opposite-branch assignments with:

```python
and_(
    AcademicTeacher.branch.isnot(None),
    func.trim(AcademicTeacher.branch) != '',
    func.lower(AcademicTeacher.branch) != normalized_branch,
)
```

Raise `TeacherReportBranchScopeError` with bounded offending teacher/class IDs before running the normal report query. Do not merely hide these rows with an allow-list predicate; explicit contamination must be visible and fail-closed.

- [ ] **Step 4: Validate branch in immutable payloads and campus ownership**

`validate_report_branch` requires every class row to carry exactly the scheduled branch. A teacher row with a non-empty branch must match; a null/empty teacher branch inherits the single class branch. Reject a teacher whose classes span branches. In `_build_campus_report_snapshots_locked`, verify each campus exists as an active `AcademicCampus(campus_code, branch)` pair before querying the report.

- [ ] **Step 5: Validate HO inputs again**

`create_ho_snapshot` must reject a campus snapshot when its database row branch, envelope branch, report teacher branch, report class branch, or campus ownership differs from the requested HO branch. Run the same assertions for both Poly and PTCD fixtures.

- [ ] **Step 6: Run report regressions**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_teacher_report_branch_isolation.py app/tests/test_academic_teacher_report_snapshots.py app/tests/test_teacher_management_all_cms_regression.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/academic/teacher_report.py backend/app/services/academic/report_snapshot.py backend/app/services/academic/daily_teacher_report_runtime.py backend/app/tests/test_academic_teacher_report_branch_isolation.py backend/app/tests/test_academic_teacher_report_snapshots.py
git commit -m "fix(academic): isolate Poly and PTCD report snapshots"
```

### Task 8: Campus and HO report stages with retry barriers

**Files:**
- Modify: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/services/academic/daily_teacher_report_runtime.py`
- Modify: `backend/app/services/academic/report_snapshot.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_reports.py`
- Modify: `backend/app/tests/test_academic_teacher_report_snapshots.py`
- Modify: `backend/app/tests/test_daily_teacher_report_pipeline_contract.py`

**Interfaces:**
- Produces: `ensure_report_attempt(db, *, root, scope, campus, stage, round_no, snapshot_id) -> AcademicTeacherReportJob`.
- Produces: `ensure_snapshot_attempt(db, *, root, scope, snapshot_type, round_no) -> AcademicBulkOperationJob`.
- Produces: `academic_daily_snapshot_attempt_task(job_id)` on `exports` for `campus_set` and `ho` snapshot attempts.
- Produces: `build_scope_campus_snapshots(scope_parent, state, source_synced_at) -> dict[str, str]` without creating HO.
- Produces: `build_scope_ho_snapshot(scope_parent, state, campus_snapshot_ids, source_synced_at) -> str` only after campus artifacts succeed.
- Consumes: Task 2 report `parent_job_id` and `idempotency_key` fields.

- [ ] **Step 1: Write failing campus-window, retry, and HO-order tests**

```python
def test_campus_exports_share_one_four_job_window_across_branches():
    root = seed_score_complete_root(campuses={'poly': 5, 'ptcd': 4})
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert count_active_report_jobs(root.id, stage='campus_reports') == 4


def test_failed_campus_retries_after_every_campus_attempt_is_terminal():
    root = seed_campus_attempts(poly_hn='failed', poly_hcm='completed', ptcd_hn='running')
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert report_attempt_count(root.id, target='poly:hn') == 1
    finish_report(root.id, target='ptcd:hn', status='completed')
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert report_attempt_count(root.id, target='poly:hn') == 2
    assert report_attempt_count(root.id, target='poly:hcm') == 1


def test_ho_is_not_created_until_every_campus_in_both_branches_succeeds():
    root = seed_campus_attempts(poly_hn='completed', ptcd_hn='failed', round_no=3)
    result = runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert result['code'] == 'stage_retry_exhausted'
    assert count_ho_jobs(root.id) == 0


def test_failed_snapshot_scope_retries_without_rebuilding_successful_scope():
    root = seed_score_complete_root(campuses={'poly': 2, 'ptcd': 1})
    seed_snapshot_attempt(root.id, scope='poly:term-1', status='completed', round_no=0)
    seed_snapshot_attempt(root.id, scope='ptcd:term-2', status='failed', round_no=0)
    runtime.run_daily_academic_pipeline(FakeCelery(), root.id)
    assert snapshot_attempt_count(root.id, scope='poly:term-1') == 1
    assert snapshot_attempt_count(root.id, scope='ptcd:term-2') == 2
```

- [ ] **Step 2: Run report pipeline tests and verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_reports.py app/tests/test_academic_teacher_report_snapshots.py -q`

Expected: FAIL because current per-term parents enqueue every campus immediately and build HO before campus workbooks finish.

- [ ] **Step 3: Split report intent creation from Celery publication**

Refactor `_create_scheduled_export_job` into an idempotent row factory and keep `_publish_scheduled_export_job` as the only publisher. Use keys:

```text
academic-daily:v2:{run_date}:{term_id}:{branch}:campus:{campus}:attempt:{round_no}
academic-daily:v2:{run_date}:{term_id}:{branch}:ho:attempt:{round_no}
```

The root row lock plus the unique report key prevents duplicates after a crash. Persist `parent_job_id=root.id`, `daily_stage`, `logical_target_key`, and `attempt_no` before publishing.

- [ ] **Step 4: Build immutable campus snapshots before campus exports**

For each branch/term scope, create one idempotent `daily_report_snapshot_attempt` bulk row and publish `academic_daily_snapshot_attempt_task` on `exports`. The task creates all campus snapshots for that scope in one existing consistent-snapshot transaction. Treat snapshot construction as a scope target inside the campus stage. Retry only failed scope targets after all snapshot targets are terminal. Once every scope snapshot exists, publish campus workbook targets globally with at most four active jobs.

- [ ] **Step 5: Move HO snapshot creation behind the campus barrier**

Do not call `_build_ho_report_snapshot` during campus snapshot creation. After every campus workbook for both branches is completed, create an `academic_daily_snapshot_attempt_task` with `snapshot_type='ho'` for each `(term_id, branch)`. A successful snapshot attempt supplies the immutable HO snapshot ID to the matching workbook attempt. Use the same three-round barrier and global window for HO snapshot and workbook attempts.

- [ ] **Step 6: Preserve truthful terminal state and provenance**

On success, root `result_json['artifacts']` stores campus and HO job IDs by scope and logical target. On exhaustion, store only completed artifact IDs as diagnostic provenance, set root status `failed`, and do not label them as the completed daily run. Keep `source_campus_report_job_ids`, campus snapshot IDs, and checksums on each HO request.

- [ ] **Step 7: Run report-stage and artifact regressions**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_reports.py app/tests/test_academic_teacher_report_snapshots.py app/tests/test_daily_teacher_report_pipeline_contract.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/academic/daily_academic_pipeline.py backend/app/services/academic/daily_teacher_report_runtime.py backend/app/services/academic/report_snapshot.py backend/app/tests/test_academic_daily_pipeline_reports.py backend/app/tests/test_academic_teacher_report_snapshots.py backend/app/tests/test_daily_teacher_report_pipeline_contract.py
git commit -m "feat(academic): retry campus and HO report stages"
```

### Task 9: Recovery, full verification, and release handoff

**Files:**
- Modify: `backend/app/services/academic/daily_academic_pipeline.py`
- Modify: `backend/app/services/academic/daily_teacher_report_runtime.py`
- Modify: `backend/app/services/academic/scheduled_parent.py`
- Create: `backend/app/tests/test_academic_daily_pipeline_recovery.py`
- Modify: `docs/superpowers/plans/2026-09-22-academic-job-report-quiz-hardening.md`

**Interfaces:**
- Produces: `recover_daily_academic_pipeline(celery_app) -> dict[str, object]`.
- Guarantees: recovery republishes the persisted continuation/attempt and never changes `stage_round` by itself.
- Guarantees: the old umbrella plan points pipeline work to this plan while leaving Quiz Tasks 11–12 pending.

- [ ] **Step 1: Write failing crash-window and duplicate-continuation tests**

```python
def test_recovery_republishes_same_attempt_without_consuming_retry_round():
    root = seed_dispatch_pending_root(stage='score_update', round_no=2, attempt_job_id='score-job-2')
    result = runtime.recover_daily_academic_pipeline(FakeCelery())
    assert result['republished'] == 1
    assert reload(root).result_json['stage_round'] == 2
    assert count_attempts(root.id, target='score:poly:term-1:class-1') == 1


def test_duplicate_root_delivery_cannot_publish_five_active_jobs():
    root = seed_root_with_pending_targets(12)
    run_concurrently(lambda: runtime.run_daily_academic_pipeline(FakeCelery(), root.id), workers=2)
    assert count_active_daily_jobs(root.id) <= 4
```

- [ ] **Step 2: Run recovery tests and verify failure**

Run: `cd backend && ../.venv/bin/python -m pytest app/tests/test_academic_daily_pipeline_recovery.py -q`

Expected: FAIL until recovery understands v2 stage/attempt state.

- [ ] **Step 3: Implement recovery and terminal diagnostics**

Scan non-terminal `DAILY_ROOT_JOB_TYPE` roots with due or unconfirmed continuations. Republish the stored task name/args/queue. When the 24-hour root runtime is exceeded, fail with `pipeline_runtime_exceeded` and preserve `phase`, `stage_round`, scope key, target key, and last child error. Do not create a retry attempt in the scanner; only the row-locked root coordinator may call `plan_stage_barrier` and increment the round.

- [ ] **Step 4: Update the umbrella plan status**

Mark Tasks 1–10 in `2026-09-22-academic-job-report-quiz-hardening.md` as completed commits, state that Tasks 6–8 are superseded by this approved v2 pipeline plan, and leave exact Quiz allocation Tasks 11–12 pending. Do not remove their acceptance criteria.

- [ ] **Step 5: Run all focused academic pipeline tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest \
  app/tests/test_academic_daily_stage_coordinator.py \
  app/tests/test_academic_daily_pipeline_schema.py \
  app/tests/test_academic_daily_pipeline_schedule.py \
  app/tests/test_academic_daily_pipeline_ap_mapping.py \
  app/tests/test_academic_daily_pipeline_provision_score.py \
  app/tests/test_academic_assessment_component_contract.py \
  app/tests/test_academic_teacher_report_branch_isolation.py \
  app/tests/test_academic_daily_pipeline_reports.py \
  app/tests/test_academic_daily_pipeline_recovery.py \
  app/tests/test_academic_scheduled_parent_recovery.py \
  app/tests/test_academic_teacher_report_snapshots.py -q
```

Expected: all selected tests PASS with zero failures.

Run: `cd frontend && npm run typecheck`

Run: `cd e2e && npx playwright test tests/student-grade-column-hygiene.spec.ts --reporter=line`

Expected: frontend typecheck and the assessment-column browser regression PASS.

- [ ] **Step 6: Run migrations, compilation, and backend regressions**

Run:

```bash
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m compileall app
../.venv/bin/python -m pytest app/tests -q
```

Expected: migration reaches `0067`, compilation exits zero, and the backend suite has zero failures. If infrastructure-dependent tests are skipped, record their exact names and reasons.

- [ ] **Step 7: Verify runtime configuration without executing production work**

Run:

```bash
cd backend
../.venv/bin/python - <<'PY'
from app.worker import celery_app

schedule = celery_app.conf.beat_schedule
assert schedule['academic-daily-pipeline-01-vn']['task'] == 'academic_daily_pipeline_start_task'
assert 'academic-ap-sync-and-auto-map-03-vn' not in schedule
assert 'academic-score-sync-all-students' not in schedule
assert celery_app.conf.timezone == 'Asia/Ho_Chi_Minh'
print('daily_pipeline_schedule_ok')
PY
```

Expected: `daily_pipeline_schedule_ok`.

- [ ] **Step 8: Review the complete diff against the spec**

Verify all six stage names, both mandatory branches, maximum four active jobs, three retry rounds, canonical Quiz/Final-test projection, branch-isolated campus/HO validation, and fail-closed transitions are covered by behavior tests. Confirm `AI-Server.zip` remains untracked and unchanged.

- [ ] **Step 9: Commit the recovery and plan-status changes**

```bash
git add backend/app/services/academic/daily_academic_pipeline.py backend/app/services/academic/daily_teacher_report_runtime.py backend/app/services/academic/scheduled_parent.py backend/app/tests/test_academic_daily_pipeline_recovery.py docs/superpowers/plans/2026-09-22-academic-job-report-quiz-hardening.md
git commit -m "test(academic): verify daily pipeline recovery"
```

- [ ] **Step 10: Push without force and report evidence**

Re-read `refs/heads/feat/import-quiz-cms-old-su26`, ensure it is the expected parent, push every local commit as a fast-forward update with `force=false`, then report focused/full test counts, migration result, final remote SHA, and any environment-only limitation.
