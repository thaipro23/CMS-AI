from types import SimpleNamespace

import pytest

import app.services.fa26_compat as compat


class _FakeWorkflow:
    def __init__(self, releases):
        self._releases = releases

    def _published_release_question_rows(self, release):
        return self._releases[str(release.id)]


def _question(qid: str, qtype: str, *, source_type: str = 'legacy_quiz_excel'):
    return SimpleNamespace(id=qid, question_type=qtype, source_type=source_type)


def test_legacy_final_preserves_source_question_types_and_does_not_filter(monkeypatch):
    release = SimpleNamespace(id='r1')
    questions = {
        'q1': _question('q1', 'single_select'),
        'q2': _question('q2', 'multi_select'),
        'q3': _question('q3', 'text_input'),
        'q4': _question('q4', 'numerical_input'),
    }
    rows = [SimpleNamespace(question_id=qid) for qid in questions]
    workflow = _FakeWorkflow({'r1': (rows, questions)})
    seen = {}

    def fake_native_plan(self, **kwargs):
        native_rows, native_questions = self._published_release_question_rows(release)
        seen['ids'] = [row.question_id for row in native_rows]
        seen['types'] = [native_questions[row.question_id].question_type for row in native_rows]
        return {
            'target_counts': {'EASY': 2, 'MEDIUM': 1, 'HARD': 1},
            'effective_target_counts': {'EASY': 2, 'MEDIUM': 1, 'HARD': 1},
            'slots': [],
        }

    monkeypatch.setattr(compat, '_ORIGINAL_FINAL_TEST_PLAN', fake_native_plan)

    plan = compat._build_final_test_plan_compat(
        workflow,
        source_releases=[release],
        source_details=[],
        total_questions=4,
        difficulty_easy=50,
        difficulty_medium=25,
        difficulty_hard=25,
    )

    assert seen['ids'] == ['q1', 'q2', 'q3', 'q4']
    assert seen['types'] == ['single_select', 'multi_select', 'text_input', 'numerical_input']
    assert plan['question_type_policy'] == 'preserve_source_types_no_quota'
    assert plan['question_type_filter_applied'] is False
    assert plan['candidate_question_type_counts'] == {
        'single_select': 1,
        'multi_select': 1,
        'text_input': 1,
        'numerical_input': 1,
    }
    assert plan['difficulty_policy'] == 'legacy_rebalance_when_capacity_short'


def test_native_final_keeps_strict_difficulty(monkeypatch):
    release = SimpleNamespace(id='r1')
    question = _question('q1', 'single_select', source_type='ai_generation')
    workflow = _FakeWorkflow({'r1': ([SimpleNamespace(question_id='q1')], {'q1': question})})

    def fake_native_plan(self, **kwargs):
        return {
            'target_counts': {'EASY': 2, 'MEDIUM': 1, 'HARD': 1},
            'effective_target_counts': {'EASY': 1, 'MEDIUM': 2, 'HARD': 1},
            'slots': [],
        }

    monkeypatch.setattr(compat, '_ORIGINAL_FINAL_TEST_PLAN', fake_native_plan)

    with pytest.raises(ValueError, match='không được tự cân lại tỷ lệ độ khó'):
        compat._build_final_test_plan_compat(
            workflow,
            source_releases=[release],
            source_details=[],
            total_questions=4,
            difficulty_easy=50,
            difficulty_medium=25,
            difficulty_hard=25,
        )
