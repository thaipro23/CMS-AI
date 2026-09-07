import pytest

from app.services.problem_bank_slot_metadata import (
    normalize_problem_bank_slot,
    normalize_problem_bank_slots,
)


def test_slot_no_is_copied_to_slot_m0():
    assert normalize_problem_bank_slot({'slot_no': 1, 'difficulty': 'EASY'}) == {
        'slot_no': 1,
        'slot_m0': 1,
        'difficulty': 'EASY',
    }


def test_slot_m0_is_copied_to_slot_no():
    assert normalize_problem_bank_slot({'slot_m0': '2'}) == {
        'slot_m0': 2,
        'slot_no': 2,
    }


def test_matching_slot_fields_are_preserved():
    normalized = normalize_problem_bank_slot({'slot_m0': 3, 'slot_no': '3'})
    assert normalized['slot_m0'] == normalized['slot_no'] == 3


def test_mismatched_or_invalid_slot_metadata_is_rejected():
    for slot in (
        {'slot_m0': 4, 'slot_no': 5},
        {'slot_no': 0},
        {'slot_m0': 'bad'},
        {},
    ):
        with pytest.raises(ValueError):
            normalize_problem_bank_slot(slot)


def test_duplicate_slot_discriminator_is_rejected():
    with pytest.raises(ValueError, match='Duplicate Problem Bank slot'):
        normalize_problem_bank_slots([
            {'slot_no': 1},
            {'slot_m0': 1},
        ])
