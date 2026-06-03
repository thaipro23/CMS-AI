from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag


_FILENAME_JSON_TAIL_RE = re.compile(r"\s*\{\s*['\"]filename['\"]\s*:\s*\[.*?\]\s*\}\s*$", re.IGNORECASE | re.DOTALL)
_FILENAME_LINE_RE = re.compile(r"(?:^|\n)\s*(?:filename|file_name)\s*:\s*\[[^\n]*\]\s*(?=\n|$)", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedProblemChoice:
    text: str
    correct: bool = False


@dataclass(frozen=True)
class ParsedProblemQuestion:
    question: str
    choices: list[ParsedProblemChoice] = field(default_factory=list)
    solution: str = ''


def normalize_problem_text(text: str) -> str:
    """Normalize extracted Open edX problem text without losing Vietnamese accents."""
    text = unescape(text or '')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_openedx_filename_metadata(text: str) -> str:
    """Remove Open edX filename metadata accidentally appended to learning text.

    Some Course Blocks/plugin payloads can leak values like
    ``{"filename": ["problem/abc.xml"]}`` or ``filename: [...]`` into the
    textual component.  Those values are source metadata, not learning content,
    so they must not appear in the UI, token counts or AI prompt.
    """
    text = text or ''
    previous = None
    cleaned = text
    while previous != cleaned:
        previous = cleaned
        cleaned = _FILENAME_JSON_TAIL_RE.sub('', cleaned)
        cleaned = _FILENAME_LINE_RE.sub('\n', cleaned)
    return cleaned.strip()


def _clean_fragment_text(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'get_text'):
        value = value.get_text(' ')
    value = remove_openedx_filename_metadata(str(value))
    value = re.sub(r"\s+", " ", unescape(value)).strip()
    return value


def _is_correct(value: Any) -> bool:
    return str(value or '').strip().lower() in {'true', '1', 'yes'}


def _direct_text_without_children(tag: Tag | None) -> str:
    if tag is None:
        return ''
    texts: list[str] = []
    for child in tag.children:
        if isinstance(child, Tag):
            continue
        text = _clean_fragment_text(child)
        if text:
            texts.append(text)
    return ' '.join(texts).strip()


def _poly_question_text(context: Tag | None) -> str:
    """Extract question text from FPT/Poly custom problem markup.

    Some CMS quizzes store the prompt in a sibling ``<div class="poly">`` and the
    answer choices in the following ``<multiplechoiceresponse>``.  The old parser
    only searched inside ``multiplechoiceresponse``, so those quizzes degraded to
    plain text and lost the correct-answer markers.
    """
    if context is None:
        return ''

    # Best source in the uploaded CMS quizzes: <pre class="poly-body">...</pre>
    body = context.find(class_=lambda value: value and 'poly-body' in str(value).split())
    if body:
        question = _clean_fragment_text(body)
        heading = context.find(['h3', 'h4'])
        heading_text = _clean_fragment_text(heading)
        if heading_text and re.match(r'^(câu|question)\s*\d+', heading_text, flags=re.IGNORECASE):
            return f'{heading_text} {question}'.strip()
        return question

    # Standard prompt tags next to the response.
    label = context.find(['label', 'legend'])
    if label:
        return _clean_fragment_text(label)

    # If no class is present, prefer <pre> or question-looking <p> text.
    pre = context.find('pre')
    if pre:
        return _clean_fragment_text(pre)

    # Avoid instruction-only text such as "Chọn một đáp án đúng".
    text = _clean_fragment_text(context)
    text = re.sub(r'\bChọn\s+một\s+đáp\s+án\s+đúng\b', '', text, flags=re.IGNORECASE).strip()
    return text


def _find_external_question_text(response: Tag) -> str:
    """Find the question prompt when it is outside the response tag."""
    # 1. Common Open edX custom shape: previous sibling div.poly contains h3/pre.
    sibling = response.previous_sibling
    hop = 0
    while sibling is not None and hop < 8:
        if isinstance(sibling, Tag):
            question = _poly_question_text(sibling)
            if question:
                return question
        sibling = sibling.previous_sibling
        hop += 1

    # 2. Sometimes the prompt is inside a previous sibling of parent container.
    parent = response.parent if isinstance(response.parent, Tag) else None
    if parent:
        sibling = parent.previous_sibling
        hop = 0
        while sibling is not None and hop < 8:
            if isinstance(sibling, Tag):
                question = _poly_question_text(sibling)
                if question:
                    return question
            sibling = sibling.previous_sibling
            hop += 1

    # 3. Fallback: use direct text just before the choicegroup inside the response.
    return _direct_text_without_children(response)


def _question_text_from_response(response: Tag) -> str:
    label = response.find(['label', 'legend'], recursive=True)
    question_text = _clean_fragment_text(label)
    if question_text:
        return question_text

    # Some authors put <p>/<pre> directly inside the response before choices.
    for candidate in response.find_all(['pre', 'p', 'div'], recursive=False):
        # Skip containers that are only choices/solution wrappers.
        if candidate.find(['choice', 'solution', 'choicehint', 'demandhint', 'hintgroup']):
            continue
        question_text = _poly_question_text(candidate)
        if question_text:
            return question_text

    question_text = _find_external_question_text(response)
    if question_text:
        return question_text

    # Best effort: remove choices/solutions then use the remaining text.
    clone = BeautifulSoup(str(response), 'html.parser')
    for tag in clone.find_all(['choice', 'solution', 'choicehint', 'demandhint', 'hintgroup']):
        tag.extract()
    return _clean_fragment_text(clone)


def _response_containers(soup: BeautifulSoup) -> list[Tag]:
    """Return one parse container per question, avoiding duplicate choicegroup parse."""
    responses = soup.find_all(['multiplechoiceresponse', 'choiceresponse'])
    if responses:
        return responses

    # Fallback for non-standard fragments where choicegroup is the top-level block.
    groups = soup.find_all(['choicegroup', 'checkboxgroup'])
    if groups:
        return groups
    return [soup]


def parse_problem_xml(problem_xml: str) -> list[ParsedProblemQuestion]:
    """Parse old Open edX problem XML into teacher-readable question data.

    Supports common CAPA shapes and FPT/Poly quizzes where each question prompt
    is stored in a ``div.poly`` immediately before ``multiplechoiceresponse``.
    When the XML is malformed, BeautifulSoup still gives a best-effort tree; if
    we cannot find choices, callers should fall back to plain text.
    """
    raw = remove_openedx_filename_metadata(problem_xml or '')
    if not raw.strip():
        return []

    soup = BeautifulSoup(raw, 'html.parser')
    questions: list[ParsedProblemQuestion] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for container in _response_containers(soup):
        choices = []
        for choice in container.find_all('choice'):
            text = _clean_fragment_text(choice)
            if not text:
                continue
            choices.append(ParsedProblemChoice(text=text, correct=_is_correct(choice.get('correct'))))

        if len(choices) < 2:
            continue

        question_text = _question_text_from_response(container)
        solution_tag = container.find('solution')
        solution = _clean_fragment_text(solution_tag)

        fingerprint = (question_text, tuple(choice.text for choice in choices))
        if not question_text or fingerprint in seen:
            continue
        seen.add(fingerprint)
        questions.append(ParsedProblemQuestion(question=question_text, choices=choices, solution=solution))

    return questions


def build_ai_text_from_problem(problem_xml: str) -> str:
    """Convert an old CMS/Open edX problem into source text for teacher UI and AI.

    The correct answer marker is intentional: it helps teachers inspect the old
    quiz and helps the model understand the canonical concept when a problem
    node/chunk is used as source.  This text is only shown in AI Server
    teacher/admin screens, not in learner-facing CMS views.
    """
    questions = parse_problem_xml(problem_xml)
    if not questions:
        return ''

    parts: list[str] = [
        '[SOURCE TYPE: EXISTING OPEN EDX PROBLEM]',
        'Tài liệu nguồn là quiz/câu hỏi cũ trong CMS. Được dùng làm nguồn kiến thức, nhưng câu hỏi AI sinh ra phải đổi cách hỏi/diễn đạt và không copy nguyên văn.',
    ]
    for index, question in enumerate(questions, start=1):
        # If the source already contains "CÂU 1", avoid rendering "Câu 1: CÂU 1".
        prefix = '' if re.match(r'^(câu|question)\s*\d+', question.question, flags=re.IGNORECASE) else f'Câu {index}: '
        parts.append(f'{prefix}{question.question}'.strip())
        for choice_index, choice in enumerate(question.choices):
            letter = chr(ord('A') + choice_index)
            marker = ' [ĐÁP ÁN ĐÚNG]' if choice.correct else ''
            parts.append(f'{letter}. {choice.text}{marker}')
        if question.solution:
            parts.append(f'Giải thích: {question.solution}')
    return '\n'.join(parts).strip()
