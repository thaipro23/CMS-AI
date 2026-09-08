from types import SimpleNamespace

import pytest

import app.services.fa26_compat as compat
from app.services.question_bank.constraint_planner import _balanced_targets, _rebalance_legacy


def test_constraint_config_can_disable_both_filters():
    token = compat.bind_quiz_constraint_request(
        {
            'difficulty_enabled': False,
            'question_type_enabled': False,
        }
    )
    try:
        config = compat.current_quiz_constraint_config()
        assert config['difficulty_enabled'] is False
        assert config['question_type_enabled'] is False
    finally:
        compat.reset_quiz_constraint_request(token)


def test_question_type_enabled_requires_100_percent():
    token = compat.bind_quiz_constraint_request(
        {
            'difficulty_enabled': True,
            'question_type_enabled': True,
            'question_type_weights': {
                'single_select': 40,
                'multi_select': 20,
                'dropdown_fill': 10,
                'text_input': 0,
                'numerical_input': 0,
            },
        }
    )
    try:
        with pytest.raises(ValueError, match='Định dạng câu phải bằng 100%'):
            compat._validated_constraint_config()
    finally:
        compat.reset_quiz_constraint_request(token)


def test_legacy_difficulty_rebalances_short_bucket_but_keeps_total():
    result = _rebalance_legacy(
        {'easy': 7, 'medium': 5, 'hard': 3},
        {'easy': 30, 'medium': 20, 'hard': 0},
        15,
    )
    assert result == {'easy': 9, 'medium': 6, 'hard': 0}
    assert sum(result.values()) == 15


def test_final_always_balances_by_release_when_filters_are_off():
    result = _balanced_targets(
        ['lesson-1', 'lesson-2', 'lesson-3'],
        {'lesson-1': 20, 'lesson-2': 20, 'lesson-3': 20},
        8,
    )
    assert result == {'lesson-1': 3, 'lesson-2': 3, 'lesson-3': 2}
    assert all(value >= 1 for value in result.values())


def test_final_rejects_total_smaller_than_source_lesson_count():
    with pytest.raises(ValueError, match='mỗi Bài có ít nhất 1 câu'):
        _balanced_targets(
            ['lesson-1', 'lesson-2', 'lesson-3'],
            {'lesson-1': 20, 'lesson-2': 20, 'lesson-3': 20},
            2,
        )


def test_runtime_final_builder_uses_request_constraint_config(monkeypatch):
    captured = {}

    def fake_builder(workflow, **kwargs):
        captured.update(kwargs)
        return {'ok': True, 'slots': []}

    monkeypatch.setattr(compat, 'build_final_constraint_plan', fake_builder)
    token = compat.bind_quiz_constraint_request(
        {
            'difficulty_enabled': False,
            'question_type_enabled': True,
            'question_type_weights': {
                'single_select': 50,
                'multi_select': 30,
                'dropdown_fill': 20,
                'text_input': 0,
                'numerical_input': 0,
            },
        }
    )
    try:
        result = compat._build_final_test_plan_compat(
            SimpleNamespace(),
            source_releases=[SimpleNamespace(id='release-1')],
            source_details=[{'release_id': 'release-1', 'chapter_title': 'Bài 1'}],
            total_questions=15,
            difficulty_easy=50,
            difficulty_medium=30,
            difficulty_hard=20,
        )
    finally:
        compat.reset_quiz_constraint_request(token)

    assert result['ok'] is True
    assert captured['config']['difficulty_enabled'] is False
    assert captured['config']['question_type_enabled'] is True
    assert captured['config']['question_type_weights']['single_select'] == 50
