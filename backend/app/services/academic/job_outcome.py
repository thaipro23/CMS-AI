from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class ClassSyncOutcome:
    ok: bool
    target_count: int
    eligible_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    failures: list[dict[str, Any]]

    @property
    def counts(self) -> dict[str, int]:
        return {
            'target_count': self.target_count,
            'eligible_count': self.eligible_count,
            'succeeded_count': self.succeeded_count,
            'skipped_count': self.skipped_count,
            'failed_count': self.failed_count,
        }


def _outcome(
    *,
    result_ok: bool,
    target: int,
    succeeded: int,
    skipped: int = 0,
    failures: list[dict[str, Any]] | None = None,
) -> ClassSyncOutcome:
    target = _count(target)
    succeeded = min(target, _count(succeeded))
    skipped = min(max(0, target - succeeded), _count(skipped))
    failed = max(0, target - succeeded - skipped)
    details = list(failures or [])[:20]
    if not result_ok and failed == 0:
        target += 1
        failed += 1
    return ClassSyncOutcome(
        ok=bool(result_ok and failed == 0),
        target_count=target,
        eligible_count=target,
        succeeded_count=succeeded,
        skipped_count=skipped,
        failed_count=failed,
        failures=details,
    )


def _combine(
    outcomes: list[ClassSyncOutcome],
    *,
    result_ok: bool,
) -> ClassSyncOutcome:
    failures = [
        detail
        for outcome in outcomes
        for detail in outcome.failures
    ][:20]
    target = sum(item.target_count for item in outcomes)
    succeeded = sum(item.succeeded_count for item in outcomes)
    skipped = sum(item.skipped_count for item in outcomes)
    failed = sum(item.failed_count for item in outcomes)
    if not result_ok and failed == 0:
        target += 1
        failed += 1
    return ClassSyncOutcome(
        ok=bool(result_ok and failed == 0),
        target_count=target,
        eligible_count=sum(item.eligible_count for item in outcomes),
        succeeded_count=succeeded,
        skipped_count=skipped,
        failed_count=failed,
        failures=failures,
    )


def _enrollment_outcome(result: dict[str, Any], *, stage: str) -> ClassSyncOutcome:
    student_target = _count(result.get('total'))
    student_succeeded = _count(result.get('updated'))
    teacher = result.get('teachers') if isinstance(result.get('teachers'), dict) else {}
    teacher_target = _count(teacher.get('total'))
    teacher_succeeded = _count(teacher.get('updated'))
    failed = max(0, student_target - student_succeeded) + max(
        0,
        teacher_target - teacher_succeeded,
    )
    failures = []
    if failed:
        failures.append({
            'stage': stage,
            'failed_count': failed,
            'message': str(result.get('message') or 'Not every enrollment target succeeded')[:1000],
        })
    return _outcome(
        result_ok=result.get('ok') is True,
        target=student_target + teacher_target,
        succeeded=student_succeeded + teacher_succeeded,
        failures=failures,
    )


def _account_outcome(result: dict[str, Any], *, stage: str) -> ClassSyncOutcome:
    counts = result.get('counts') if isinstance(result.get('counts'), dict) else {}
    target = _count(result.get('total'))
    succeeded = _count(counts.get('matched'))
    teacher = result.get('teachers') if isinstance(result.get('teachers'), dict) else {}
    teacher_counts = teacher.get('counts') if isinstance(teacher.get('counts'), dict) else {}
    teacher_target = _count(teacher.get('total'))
    teacher_succeeded = _count(teacher_counts.get('matched'))
    failed = max(0, target - succeeded) + max(0, teacher_target - teacher_succeeded)
    failures = []
    if failed:
        failures.append({
            'stage': stage,
            'failed_count': failed,
            'message': str(result.get('message') or 'Not every CMS account target matched')[:1000],
        })
    outcomes = [
        _outcome(
            result_ok=result.get('ok') is True,
            target=target + teacher_target,
            succeeded=succeeded + teacher_succeeded,
            failures=failures,
        )
    ]
    enrollment = result.get('enrollment')
    if isinstance(enrollment, dict):
        outcomes.append(_enrollment_outcome(enrollment, stage=f'{stage}.enrollment'))
    return _combine(outcomes, result_ok=result.get('ok') is True)


def _learning_outcome(result: dict[str, Any], *, stage: str) -> ClassSyncOutcome:
    connector = (
        result.get('connector_counts')
        if isinstance(result.get('connector_counts'), dict)
        else {}
    )
    target = _count(connector.get('checked', result.get('updated', result.get('total'))))
    missing = min(target, _count(connector.get('missing_result')))
    succeeded = max(0, target - missing)
    failures = []
    if missing:
        failures.append({
            'stage': stage,
            'failed_count': missing,
            'message': 'Connector omitted one or more requested learners.',
        })
    return _outcome(
        result_ok=result.get('ok') is True,
        target=target,
        succeeded=succeeded,
        failures=failures,
    )


def evaluate_class_sync_result(
    job_type: str,
    result: Any,
) -> ClassSyncOutcome:
    if not isinstance(result, dict):
        return _outcome(
            result_ok=False,
            target=1,
            succeeded=0,
            failures=[{'stage': 'result', 'message': 'Service returned a non-object result.'}],
        )

    normalized_type = str(job_type or '').strip().lower()
    if normalized_type == 'cms_sync_check':
        return _account_outcome(result, stage='cms_users')
    if normalized_type == 'cms_enrollment_sync':
        return _enrollment_outcome(result, stage='enrollment')
    if normalized_type == 'learning_sync':
        return _learning_outcome(result, stage='learning')
    if normalized_type == 'full_cms_sync':
        mapping = result.get('mapping') if isinstance(result.get('mapping'), dict) else {}
        mapping_ok = bool(
            mapping.get('ok') is True
            and str(result.get('status') or '').strip().lower() == 'completed'
        )
        mapping_outcome = _outcome(
            result_ok=mapping_ok,
            target=1,
            succeeded=1 if mapping_ok else 0,
            failures=[] if mapping_ok else [{
                'stage': 'mapping',
                'failed_count': 1,
                'message': str(
                    mapping.get('message')
                    or result.get('message')
                    or 'Course mapping did not complete.'
                )[:1000],
            }],
        )
        outcomes = [mapping_outcome]
        cms_users = result.get('cms_users')
        enrollment = result.get('enrollment')
        learning = result.get('learning')
        if isinstance(cms_users, dict):
            outcomes.append(_account_outcome(cms_users, stage='cms_users'))
        elif mapping_ok:
            outcomes.append(_outcome(
                result_ok=False,
                target=1,
                succeeded=0,
                failures=[{'stage': 'cms_users', 'message': 'Missing mandatory CMS-account result.'}],
            ))
        if isinstance(enrollment, dict):
            outcomes.append(_enrollment_outcome(enrollment, stage='enrollment'))
        elif mapping_ok:
            outcomes.append(_outcome(
                result_ok=False,
                target=1,
                succeeded=0,
                failures=[{'stage': 'enrollment', 'message': 'Missing mandatory enrollment result.'}],
            ))
        if isinstance(learning, dict):
            outcomes.append(_learning_outcome(learning, stage='learning'))
        return _combine(
            outcomes,
            result_ok=result.get('ok') is True and mapping_ok,
        )
    return _outcome(
        result_ok=False,
        target=1,
        succeeded=0,
        failures=[{'stage': 'job_type', 'message': f'Unsupported job type: {normalized_type}'}],
    )


def automatic_retry_allowed(job_type: str, *, transient: bool) -> bool:
    return bool(transient and str(job_type or '').strip().lower() == 'learning_sync')


class ClassSyncOutcomeError(RuntimeError):
    def __init__(self, result: dict[str, Any], outcome: ClassSyncOutcome):
        self.outcome = outcome
        self.result = {
            **result,
            'ok': False,
            'code': 'CLASS_SYNC_INCOMPLETE',
            'outcome_counts': outcome.counts,
            'failure_details': outcome.failures,
        }
        super().__init__(
            'Class sync did not satisfy every mandatory target '
            f'({outcome.succeeded_count}/{outcome.target_count} succeeded).'
        )
