from types import SimpleNamespace
from datetime import datetime

from app.services.training_policy_service import TrainingPolicyService


def _cls(start='2026-05-11', end='2026-06-27'):
    return SimpleNamespace(id='class-1', start_date=start, end_date=end)


def _quiz(number, percent=None, submitted_at=None, deadline='2026-05-16', available_from='2026-05-11'):
    return {
        'name': f'Quiz {number}',
        'quiz_number': number,
        'percent': percent,
        'submitted_at': submitted_at,
        'deadline_date': deadline,
        'available_from': available_from,
    }


def _service():
    return TrainingPolicyService(db=SimpleNamespace())


def test_quiz_100_on_time_is_passed():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-15')], overrides={})
    assert result['exam_status'] == 'eligible'
    assert result['quiz_passed_count'] == 1


def test_quiz_100_after_deadline_is_not_eligible():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-17')], overrides={})
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_late_count'] == 1


def test_quiz_80_before_deadline_is_not_eligible():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 80, '2026-05-15')], overrides={})
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_failed_count'] == 1


def test_quiz_not_attempted_after_deadline_is_late():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, None, None, '2020-05-16')], overrides={})
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_late_count'] == 1
    assert result['quiz_not_attempted_count'] == 1


def test_quiz_100_without_submitted_at_is_insufficient_data():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 100, None)], overrides={})
    assert result['exam_status'] == 'insufficient_data'
    assert result['quiz_missing_deadline_count'] == 1


def test_quiz_submitted_before_available_from_is_not_eligible():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-10')], overrides={})
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_early_count'] == 1


def test_block_over_49_days_requires_manual_deadline():
    result = _service().evaluate_student(cls=_cls(end='2026-07-20'), student_id='s1', components=[_quiz(1, 100, '2026-05-15')], overrides={})
    assert result['deadline_mode'] == 'manual_required'
    assert result['exam_status'] == 'insufficient_data'


def test_assignment_graded_without_score_blocks_exam():
    assignment = SimpleNamespace(defense_status='graded', score_10=None, note='')
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[_quiz(1, 100, '2026-05-15'), {'name': 'Assignment'}],
        assignment_score=assignment,
        overrides={},
    )
    assert result['exam_status'] == 'not_eligible'
    assert result['assignment_status'] == 'graded_missing_score'


def test_assignment_not_graded_blocks_exam():
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[_quiz(1, 100, '2026-05-15'), {'name': 'Assignment'}],
        overrides={},
    )
    assert result['exam_status'] == 'not_eligible'
    assert result['assignment_status'] == 'not_graded'


def test_final_test_rule_is_not_applied_yet():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-15'), {'name': 'Final test'}], overrides={})
    assert result['final_test_rule'] == 'pending'
    assert result['exam_status'] == 'eligible'


def test_quiz_usage_key_number_does_not_create_phantom_quiz():
    # Storage keys like block@quiz-14 are not human quiz labels. They must not
    # create a Quiz 14 policy item when the real UI has only generic `Quiz`.
    component = {
        'name': 'Quiz',
        'key': 'block-v1:FPT+COM1071+SU26+type@sequential+block@quiz-14-random',
        'category': 'quiz',
        'percent': 100,
        'submitted_at': '2026-05-15',
        'deadline_date': '2026-05-16',
        'available_from': '2026-05-11',
    }
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[component], overrides={})
    assert result['quiz_total'] == 0
    assert result['exam_status'] == 'insufficient_data'



def test_quiz_below_100_without_submitted_at_is_not_eligible_not_insufficient():
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[_quiz(1, 80, None)], overrides={})
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_failed_count'] == 1
    assert result['quiz_missing_deadline_count'] == 0


def test_quiz_itembank_shell_without_quiz_number_is_ignored_for_policy():
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[{'name': 'Problem Bank EASY', 'category': 'itembank', 'percent': None}],
        overrides={},
    )
    assert result['quiz_total'] == 0
    assert result['exam_status'] == 'insufficient_data'
