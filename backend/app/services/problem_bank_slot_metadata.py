from __future__ import annotations

from typing import Any


def _positive_slot_number(value: Any, field_name: str) -> int | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError(f'{field_name} must be a positive integer')
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be a positive integer') from exc
    if number <= 0 or str(value).strip() not in {str(number), f'+{number}'}:
        raise ValueError(f'{field_name} must be a positive integer')
    return number


def normalize_problem_bank_slot(slot: dict[str, Any]) -> dict[str, Any]:
    """Return one slot with a stable slot_m0/slot_no discriminator contract."""
    if not isinstance(slot, dict):
        raise ValueError('Problem Bank slot must be an object')
    slot_m0 = _positive_slot_number(slot.get('slot_m0'), 'slot_m0')
    slot_no = _positive_slot_number(slot.get('slot_no'), 'slot_no')
    if slot_m0 is None and slot_no is None:
        raise ValueError('Problem Bank slot requires slot_m0 or slot_no')
    if slot_m0 is not None and slot_no is not None and slot_m0 != slot_no:
        raise ValueError(f'Problem Bank slot metadata mismatch: slot_m0={slot_m0}, slot_no={slot_no}')
    resolved = slot_m0 if slot_m0 is not None else slot_no
    return {**slot, 'slot_m0': resolved, 'slot_no': resolved}


def normalize_problem_bank_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize all slots and reject duplicate discriminator values."""
    if not isinstance(slots, list) or not slots:
        raise ValueError('Problem Bank slots must be a non-empty list')
    normalized = [normalize_problem_bank_slot(slot) for slot in slots]
    slot_numbers = [slot['slot_m0'] for slot in normalized]
    duplicates = sorted({number for number in slot_numbers if slot_numbers.count(number) > 1})
    if duplicates:
        raise ValueError(f'Duplicate Problem Bank slot discriminator(s): {duplicates}')
    return normalized
