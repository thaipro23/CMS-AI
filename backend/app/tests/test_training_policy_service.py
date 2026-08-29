from types import SimpleNamespace
from datetime import date

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


def test_quiz_100_on_progress_deadline_is_passed():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-15')], overrides={}, now=date(2026, 5, 15)
    )
    assert result['exam_status'] == 'eligible'
    assert result['quiz_passed_count'] == 1
    assert result['exam_cutoff_date'] == '2026-06-27'


def test_quiz_100_after_progress_deadline_but_before_final_day_is_warning_only():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-17')], overrides={}, now=date(2026, 5, 20)
    )
    assert result['exam_status'] == 'eligible'
    assert result['quiz_late_count'] == 1
    assert result['quiz_failed_count'] == 0
    assert result['quiz_results'][0]['status'] == 'completed_after_progress_deadline'


def test_quiz_80_after_progress_deadline_but_before_final_day_is_not_banned():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 80, '2026-05-15')], overrides={}, now=date(2026, 5, 20)
    )
    assert result['exam_status'] == 'eligible'
    assert result['exam_eligible'] is True
    assert result['quiz_failed_count'] == 0
    assert result['quiz_late_count'] == 1


def test_on_final_day_student_is_still_not_banned():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 80, '2026-05-15')], overrides={}, now=date(2026, 6, 27)
    )
    assert result['exam_status'] == 'eligible'
    assert result['exam_cutoff_expired'] is False


def test_after_final_day_quiz_below_100_is_not_eligible():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 80, '2026-05-15')], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_failed_count'] == 1


def test_after_final_day_not_attempted_is_not_eligible():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, None, None)], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_not_attempted_count'] == 1
    assert result['quiz_failed_count'] == 1


def test_100_after_progress_deadline_but_before_final_day_remains_eligible_after_cutoff():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-06-20')], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'eligible'
    assert result['quiz_late_count'] == 1
    assert result['quiz_failed_count'] == 0


def test_100_only_after_final_day_is_not_eligible():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-06-28')], overrides={}, now=date(2026, 6, 29)
    )
    assert result['exam_status'] == 'not_eligible'
    assert result['quiz_failed_count'] == 1


def test_full_score_without_submitted_at_after_final_day_is_insufficient_not_false_ban():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, None)], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'insufficient_data'
    assert result['quiz_failed_count'] == 0


def test_early_attempt_is_warning_not_exam_ban():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-10')], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'eligible'
    assert result['quiz_early_count'] == 1
    assert result['quiz_failed_count'] == 0


def test_progress_deadline_manual_required_does_not_ban_before_final_day():
    result = _service().evaluate_student(
        cls=_cls(end='2026-07-20'), student_id='s1', components=[_quiz(1, 80, '2026-05-15')], overrides={}, now=date(2026, 6, 1)
    )
    assert result['deadline_mode'] == 'manual_required'
    assert result['exam_status'] == 'eligible'


def test_missing_final_day_is_insufficient_data():
    cls = SimpleNamespace(id='class-1', start_date='2026-05-11', end_date=None)
    result = _service().evaluate_student(
        cls=cls, student_id='s1', components=[_quiz(1, 100, '2026-05-15')], overrides={}, now=date(2026, 6, 28)
    )
    assert result['exam_status'] == 'insufficient_data'
    assert result['exam_cutoff_date'] is None


def test_assignment_graded_without_score_does_not_block_exam():
    assignment = SimpleNamespace(defense_status='graded', score_10=None, note='')
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[_quiz(1, 100, '2026-05-15'), {'name': 'Assignment'}],
        assignment_score=assignment,
        overrides={},
        now=date(2026, 6, 28),
    )
    assert result['exam_status'] == 'eligible'
    assert result['assignment_status'] == 'graded_missing_score'
    assert result['assignment_blocks_exam'] is False


def test_assignment_not_graded_does_not_block_exam():
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[_quiz(1, 100, '2026-05-15'), {'name': 'Assignment'}],
        overrides={},
        now=date(2026, 6, 28),
    )
    assert result['exam_status'] == 'eligible'
    assert result['assignment_status'] == 'not_graded'
    assert result['assignment_blocks_exam'] is False


def test_final_test_rule_is_not_applied_yet():
    result = _service().evaluate_student(
        cls=_cls(), student_id='s1', components=[_quiz(1, 100, '2026-05-15'), {'name': 'Final test'}], overrides={}
    )
    assert result['final_test_rule'] == 'pending'
    assert result['exam_status'] == 'eligible'


def test_quiz_usage_key_number_does_not_create_phantom_quiz():
    component = {
        'name': 'Quiz',
        'key': 'block-v1:FPT+COM1071+SU26+type@sequential+block@quiz-14-random',
        'category': 'quiz',
        'percent': 100,
        'submitted_at': '2026-05-15',
        'deadline_date': '2026-05-16',
        'available_from': '2026-05-11',
    }
    result = _service().evaluate_student(cls=_cls(), student_id='s1', components=[component], overrides={}, now=date(2026, 5, 20))
    assert result['quiz_total'] == 0
    # Before the final day, no quiz data still must not create a false exam ban.
    assert result['exam_status'] == 'eligible'


def test_quiz_itembank_shell_without_quiz_number_is_ignored_for_policy():
    result = _service().evaluate_student(
        cls=_cls(),
        student_id='s1',
        components=[{'name': 'Problem Bank EASY', 'category': 'itembank', 'percent': None}],
        overrides={},
        now=date(2026, 5, 20),
    )
    assert result['quiz_total'] == 0
    assert result['exam_status'] == 'eligible'
