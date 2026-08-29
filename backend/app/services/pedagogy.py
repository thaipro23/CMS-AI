from __future__ import annotations

import re
from typing import Any

LETTERS = ('A', 'B', 'C', 'D')


def _compact(value: object, max_len: int) -> str:
    text = ' '.join(str(value or '').split()).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + '…'


def _norm(value: object) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _contains_answer_leak(text: str, correct_answer: str | None, options: dict[str, str] | None) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False
    leak_markers = (
        'đáp án đúng', 'câu trả lời đúng', 'correct answer', 'the answer is',
        'chọn đáp án', 'chọn phương án',
    )
    if any(marker in normalized for marker in leak_markers):
        return True
    label = str(correct_answer or '').strip().upper()
    if label in LETTERS:
        # Only reject explicit answer-label language, not ordinary letter usage.
        label_patterns = (
            rf'\bđáp án\s+{label.lower()}\b',
            rf'\bphương án\s+{label.lower()}\b',
            rf'\banswer\s+{label.lower()}\b',
        )
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in label_patterns):
            return True
        correct_text = _norm((options or {}).get(label))
        # Avoid copying the complete correct option into pre-answer hints. Very
        # short option texts are ignored because substring matching is noisy.
        if len(correct_text) >= 6 and correct_text in normalized:
            return True
    return False


def normalize_pedagogy(
    raw: Any,
    *,
    correct_answer: str | None = None,
    options: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Normalize compact misconception metadata.

    Keep the learner hint deliberately compact. New generations produce one
    short indirect knowledge clue plus concise misconception labels. ``clue``
    is retained only for backward compatibility with an earlier UAT candidate.
    """
    data = raw if isinstance(raw, dict) else {}
    hint = _compact(data.get('hint'), 180)
    if _contains_answer_leak(hint, correct_answer, options):
        hint = ''
    clue = _compact(data.get('clue'), 180)
    if _contains_answer_leak(clue, correct_answer, options):
        clue = ''

    raw_misconceptions = data.get('misconceptions') if isinstance(data.get('misconceptions'), dict) else {}
    misconceptions: dict[str, str] = {}
    correct = str(correct_answer or '').strip().upper()
    for label in LETTERS:
        text = _compact(raw_misconceptions.get(label), 120)
        misconceptions[label] = '' if label == correct else text

    return {
        'hint': hint,
        'clue': clue,
        'misconceptions': misconceptions,
    }


def remap_pedagogy_after_shuffle(
    raw: Any,
    source_label_by_new_label: dict[str, str] | None,
    new_correct_answer: str | None,
) -> dict[str, Any]:
    """Move misconception metadata with option text after deterministic shuffle."""
    data = raw if isinstance(raw, dict) else {}
    raw_misconceptions = data.get('misconceptions') if isinstance(data.get('misconceptions'), dict) else {}
    label_map = source_label_by_new_label or {label: label for label in LETTERS}
    remapped = {
        new_label: str(raw_misconceptions.get(label_map.get(new_label, new_label)) or '').strip()
        for new_label in LETTERS
    }
    correct = str(new_correct_answer or '').strip().upper()
    if correct in remapped:
        remapped[correct] = ''
    return {
        'hint': str(data.get('hint') or '').strip(),
        'clue': str(data.get('clue') or '').strip(),
        'misconceptions': remapped,
    }


def _focus(question: Any) -> str:
    return _compact(
        getattr(question, 'concept_title', None)
        or getattr(question, 'learning_objective', None)
        or getattr(question, 'topic', None)
        or getattr(question, 'chapter_title', None),
        150,
    )


def _content_tokens(value: object) -> set[str]:
    text = _norm(value)
    tokens = re.findall(r"[a-zA-ZÀ-ỹ0-9_+-]+", text)
    stop = {
        'là', 'và', 'của', 'cho', 'để', 'một', 'các', 'có', 'trong', 'được',
        'the', 'a', 'an', 'to', 'of', 'for', 'is', 'are', 'in', 'on', 'with',
    }
    return {token for token in tokens if len(token) > 1 and token not in stop}


def _safe_indirect_hint(
    value: object,
    *,
    correct_answer: str | None = None,
    options: dict[str, str] | None = None,
) -> str:
    """Return one short knowledge clue without handing over the answer.

    This is intentionally conservative: explicit answer language, the complete
    correct option, or near-verbatim reuse of the correct option is rejected.
    Semantic non-leakage is primarily enforced in the generation prompt; this
    local guard provides a deterministic last line of defence at publish time.
    """
    text = _compact(value, 180)
    if not text or _contains_answer_leak(text, correct_answer, options):
        return ''

    label = str(correct_answer or '').strip().upper()
    correct_text = str((options or {}).get(label) or '').strip()
    hint_tokens = _content_tokens(text)
    answer_tokens = _content_tokens(correct_text)
    if answer_tokens:
        coverage = len(hint_tokens & answer_tokens) / len(answer_tokens)
        # Short options are especially easy to reveal with a paraphrase. Be
        # stricter there; longer options tolerate some shared domain language.
        threshold = 0.5 if len(answer_tokens) <= 4 else 0.8
        if coverage >= threshold:
            return ''
    return text


def build_hint_texts(question: Any) -> list[str]:
    """Render exactly one friendly, indirect knowledge hint.

    The hint is generated as a compact pedagogy field because raw source
    evidence can easily restate the answer. We never derive learner hints from
    explanation/source evidence at publish time. Older rows may use the legacy
    ``clue`` only when it passes the same local answer-leak guard.
    """
    options = {
        'A': str(getattr(question, 'option_a', '') or ''),
        'B': str(getattr(question, 'option_b', '') or ''),
        'C': str(getattr(question, 'option_c', '') or ''),
        'D': str(getattr(question, 'option_d', '') or ''),
    }
    correct = str(getattr(question, 'correct_answer', '') or '').strip().upper()
    pedagogy = normalize_pedagogy(
        getattr(question, 'pedagogy_json', None),
        correct_answer=correct,
        options=options,
    )
    hint = _safe_indirect_hint(
        pedagogy.get('hint'), correct_answer=correct, options=options
    )
    if not hint:
        hint = _safe_indirect_hint(
            pedagogy.get('clue'), correct_answer=correct, options=options
        )
    if not hint:
        return []
    return [f'Gợi ý nhỏ: {hint}']

def build_choice_feedback(question: Any, label: str) -> str:
    """Render concise answer-specific feedback for native Open edX choicehint."""
    label = str(label or '').strip().upper()
    correct = str(getattr(question, 'correct_answer', '') or '').strip().upper()
    focus = _focus(question)
    options = {
        'A': str(getattr(question, 'option_a', '') or ''),
        'B': str(getattr(question, 'option_b', '') or ''),
        'C': str(getattr(question, 'option_c', '') or ''),
        'D': str(getattr(question, 'option_d', '') or ''),
    }
    pedagogy = normalize_pedagogy(
        getattr(question, 'pedagogy_json', None),
        correct_answer=correct,
        options=options,
    )
    if label == correct:
        return 'Đúng. Bạn đã nhận diện đúng kiến thức/quy tắc cần dùng. Hãy đọc phần giải thích để củng cố lý do.'

    misconception = str((pedagogy.get('misconceptions') or {}).get(label) or '').strip()
    if misconception:
        tail = f' Hãy đối chiếu lại “{focus}”.' if focus else ' Hãy đối chiếu lại quy tắc cốt lõi.'
        return f'Chưa đúng: {misconception}.{tail}'
    if focus:
        return f'Chưa đúng. Phương án này chưa phù hợp với “{focus}”. Hãy kiểm tra lại dấu hiệu hoặc quy tắc cốt lõi.'
    return 'Chưa đúng. Hãy kiểm tra lại đặc điểm hoặc quy tắc cốt lõi rồi so sánh các phương án một lần nữa.'


def remap_pedagogy_after_multi_shuffle(raw: Any, source_label_by_new_label: dict[str, str] | None, new_correct_answers: list[str] | tuple[str, ...] | set[str]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    raw_misconceptions = data.get('misconceptions') if isinstance(data.get('misconceptions'), dict) else {}
    label_map = source_label_by_new_label or {label: label for label in LETTERS}
    correct = {str(value or '').strip().upper() for value in new_correct_answers or []}
    remapped = {new_label: '' if new_label in correct else str(raw_misconceptions.get(label_map.get(new_label, new_label)) or '').strip() for new_label in LETTERS}
    return {'hint': str(data.get('hint') or '').strip(), 'clue': str(data.get('clue') or '').strip(), 'misconceptions': remapped}
