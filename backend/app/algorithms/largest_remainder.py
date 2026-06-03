from __future__ import annotations

from dataclasses import dataclass
from math import floor


DIFFICULTIES = ('easy', 'medium', 'hard')
DEFAULT_DIFFICULTY_PERCENTAGES = {'easy': 50.0, 'medium': 30.0, 'hard': 20.0}


@dataclass(frozen=True)
class DifficultyAllocation:
    difficulty: str
    percent: float
    raw_count: float
    base_count: int
    remainder: float
    question_count: int


def normalize_percentages(percentages: dict[str, float] | None = None) -> dict[str, float]:
    """Return sane easy/medium/hard percentages that sum to 100.

    Frontend defaults to 50/30/20, but this function protects backend callers
    from empty, negative or typo values. Values are normalized instead of
    blindly trusting the client.
    """
    source = percentages or DEFAULT_DIFFICULTY_PERCENTAGES
    cleaned = {name: max(float(source.get(name, 0) or 0), 0.0) for name in DIFFICULTIES}
    total = sum(cleaned.values())
    if total <= 0:
        return DEFAULT_DIFFICULTY_PERCENTAGES.copy()
    return {name: cleaned[name] / total * 100.0 for name in DIFFICULTIES}


def allocate_by_largest_remainder(total_questions: int, percentages: dict[str, float] | None = None) -> list[DifficultyAllocation]:
    """Allocate integer question counts with the Largest Remainder Method.

    Steps:
    1. raw_count = total * percent / 100
    2. take floor(raw_count)
    3. calculate missing questions
    4. give missing questions to the largest remainders

    Example: 7 questions with 50/30/20 = 3.5/2.1/1.4 -> 3/2/1 + 1 to easy.
    """
    total_questions = max(int(total_questions or 0), 0)
    normalized = normalize_percentages(percentages)
    rows: list[dict] = []
    allocated = 0
    for order, difficulty in enumerate(DIFFICULTIES):
        percent = normalized[difficulty]
        raw = total_questions * percent / 100.0
        base = int(floor(raw))
        allocated += base
        rows.append({
            'difficulty': difficulty,
            'percent': percent,
            'raw_count': raw,
            'base_count': base,
            'remainder': raw - base,
            'question_count': base,
            'order': order,
        })

    missing = total_questions - allocated
    # Tie-breaker order is deterministic: larger remainder first, then easy -> medium -> hard.
    for row in sorted(rows, key=lambda item: (-item['remainder'], item['order']))[:missing]:
        row['question_count'] += 1

    return [
        DifficultyAllocation(
            difficulty=row['difficulty'],
            percent=round(row['percent'], 6),
            raw_count=row['raw_count'],
            base_count=row['base_count'],
            remainder=row['remainder'],
            question_count=row['question_count'],
        )
        for row in rows
    ]


def allocation_as_dicts(total_questions: int, percentages: dict[str, float] | None = None) -> list[dict]:
    return [allocation.__dict__ for allocation in allocate_by_largest_remainder(total_questions, percentages)]
