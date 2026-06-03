from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Any

LETTERS = ['A', 'B', 'C', 'D']


@dataclass
class NormalizedAnswers:
    options: dict[str, str]
    correct_answer: str
    changed: bool = False
    reason: str | None = None


def _clean_answer_label(value: Any) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    upper = text.upper()
    if upper in LETTERS:
        return upper
    m = re.match(r'^(?:OPTION[_\s-]?|ĐÁP ÁN\s*)?([ABCD])(?:[\).:\s-].*)?$', upper)
    return m.group(1) if m else None


def _seed_for_item(question_text: str, *, source_node_id: str | None, difficulty: str | None, index: int = 0) -> int:
    raw = f'{question_text}|{source_node_id or ""}|{difficulty or ""}|{index}'.encode('utf-8')
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def normalize_and_shuffle_options(item: dict, *, index: int = 0, force_shuffle: bool = True) -> NormalizedAnswers:
    """Normalize answer labels and shuffle option positions in backend.

    The model may always put the correct answer at A. Backend owns the final
    A/B/C/D order so exported OLX and review UI are not biased.
    """
    options = item.get('options') or {
        'A': item.get('option_a'),
        'B': item.get('option_b'),
        'C': item.get('option_c'),
        'D': item.get('option_d'),
    }
    normalized_options = {letter: str(options.get(letter) or '').strip() for letter in LETTERS}
    raw_correct = item.get('correct_answer')
    correct_letter = _clean_answer_label(raw_correct)

    # If the model returned the correct text instead of A/B/C/D, map it back.
    if not correct_letter:
        correct_text = str(raw_correct or '').strip().lower()
        for letter, text in normalized_options.items():
            if correct_text and str(text or '').strip().lower() == correct_text:
                correct_letter = letter
                break
    correct_letter = correct_letter or 'A'
    correct_text = normalized_options.get(correct_letter, '')

    if not force_shuffle:
        return NormalizedAnswers(normalized_options, correct_letter, changed=False)

    question_text = item.get('question') or item.get('question_text') or ''
    source_node_id = item.get('source_node_id') or item.get('block_id') or (item.get('source') or {}).get('block_id')
    difficulty = item.get('difficulty') or 'easy'
    rng = random.Random(_seed_for_item(question_text, source_node_id=source_node_id, difficulty=difficulty, index=index))
    order = LETTERS[:]
    rng.shuffle(order)
    if order == LETTERS:
        # Avoid no-op shuffle for many similar inputs.
        shift = (_seed_for_item(question_text, source_node_id=source_node_id, difficulty=difficulty, index=index + 99) % 3) + 1
        order = LETTERS[shift:] + LETTERS[:shift]

    shuffled = {new_letter: normalized_options[old_letter] for new_letter, old_letter in zip(LETTERS, order)}
    new_correct = next((new_letter for new_letter, text in shuffled.items() if text == correct_text), correct_letter)
    changed = shuffled != normalized_options or new_correct != correct_letter
    return NormalizedAnswers(shuffled, new_correct, changed=changed, reason='answer_randomized' if changed else None)


def answer_position_distribution(questions: list[dict]) -> dict[str, int]:
    counts = {letter: 0 for letter in LETTERS}
    for item in questions:
        letter = _clean_answer_label(item.get('correct_answer'))
        if letter:
            counts[letter] += 1
    return counts
