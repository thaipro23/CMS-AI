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
    question_type: str = 'single_select'
    choices: list[ParsedProblemChoice] = field(default_factory=list)
    accepted_answers: list[str] = field(default_factory=list)
    case_sensitive: bool = False
    string_response_type: str = 'ci'
    numerical_answer: str | None = None
    numerical_tolerance: str = '0'
    numerical_tolerance_type: str = 'absolute'
    solution: str = ''
    warnings: list[str] = field(default_factory=list)


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
    responses = soup.find_all(['multiplechoiceresponse', 'choiceresponse', 'stringresponse', 'numericalresponse'])
    if responses:
        return responses
    groups = soup.find_all(['choicegroup', 'checkboxgroup'])
    if groups:
        return groups
    return [soup]


def _solution_for_container(container: Tag) -> str:
    solution_tag = container.find('solution')
    if solution_tag:
        return _clean_fragment_text(solution_tag)
    parent = container.parent if isinstance(container.parent, Tag) else None
    if parent:
        solution_tag = parent.find('solution')
    return _clean_fragment_text(solution_tag)


def _parse_tolerance(value: object) -> tuple[str, str]:
    text = str(value or '').strip()
    if not text:
        return '0', 'absolute'
    if text.endswith('%'):
        return text[:-1].strip() or '0', 'percent'
    return text, 'absolute'


def parse_problem_xml(problem_xml: str) -> list[ParsedProblemQuestion]:
    raw = remove_openedx_filename_metadata(problem_xml or '')
    if not raw.strip():
        return []
    soup = BeautifulSoup(raw, 'html.parser')
    questions: list[ParsedProblemQuestion] = []
    seen: set[tuple] = set()
    for container in _response_containers(soup):
        tag_name = str(getattr(container, 'name', '') or '').lower()
        question_text = _question_text_from_response(container)
        if not question_text:
            continue
        solution = _solution_for_container(container)
        warnings: list[str] = []
        if tag_name in {'multiplechoiceresponse','choiceresponse','choicegroup','checkboxgroup'} or container.find(['choicegroup','checkboxgroup']):
            checkbox = tag_name == 'checkboxgroup' or container.find('checkboxgroup') is not None
            choices = [ParsedProblemChoice(text=_clean_fragment_text(choice), correct=_is_correct(choice.get('correct'))) for choice in container.find_all('choice') if _clean_fragment_text(choice)]
            if len(choices) < 2:
                continue
            correct_count = sum(1 for choice in choices if choice.correct)
            if checkbox or correct_count > 1:
                qtype = 'multi_select'
                if correct_count < 2: warnings.append('checkboxgroup có ít hơn 2 đáp án được đánh dấu đúng.')
            else:
                qtype = 'single_select'
                if correct_count != 1: warnings.append('single-select không có đúng 1 đáp án được đánh dấu đúng.')
            fingerprint=(qtype,question_text,tuple((c.text,c.correct) for c in choices))
            if fingerprint in seen: continue
            seen.add(fingerprint)
            questions.append(ParsedProblemQuestion(question=question_text,question_type=qtype,choices=choices,solution=solution,warnings=warnings)); continue
        if tag_name == 'stringresponse':
            response_mode=str(container.get('type') or 'ci').strip().lower(); answers=[]
            primary=_clean_fragment_text(container.get('answer'))
            if primary: answers.append(primary)
            for node in container.find_all('additional_answer'):
                value=_clean_fragment_text(node.get('answer') or node)
                if value and value not in answers: answers.append(value)
            if not answers: warnings.append('stringresponse không có đáp án chấp nhận.')
            if response_mode not in {'ci','cs'}: warnings.append(f'stringresponse type={response_mode} chưa được canonical editor hỗ trợ.')
            fingerprint=('text_input',question_text,tuple(answers),response_mode)
            if fingerprint in seen: continue
            seen.add(fingerprint)
            questions.append(ParsedProblemQuestion(question=question_text,question_type='text_input',accepted_answers=answers,case_sensitive=response_mode=='cs',string_response_type=response_mode,solution=solution,warnings=warnings)); continue
        if tag_name == 'numericalresponse':
            answer=_clean_fragment_text(container.get('answer')); tolerance='0'; tolerance_type='absolute'
            for param in container.find_all('responseparam'):
                if str(param.get('type') or '').strip().lower() == 'tolerance':
                    tolerance,tolerance_type=_parse_tolerance(param.get('default') or param.get('value')); break
            if not answer: warnings.append('numericalresponse không có answer.')
            fingerprint=('numerical_input',question_text,answer,tolerance,tolerance_type)
            if fingerprint in seen: continue
            seen.add(fingerprint)
            questions.append(ParsedProblemQuestion(question=question_text,question_type='numerical_input',numerical_answer=answer or None,numerical_tolerance=tolerance,numerical_tolerance_type=tolerance_type,solution=solution,warnings=warnings))
    return questions


def build_ai_text_from_problem(problem_xml: str) -> str:
    questions = parse_problem_xml(problem_xml)
    if not questions:
        return ''
    parts = ['[SOURCE TYPE: EXISTING OPEN EDX PROBLEM]','Tài liệu nguồn là quiz/câu hỏi cũ trong CMS. Được dùng làm nguồn kiến thức, nhưng câu hỏi AI sinh ra phải đổi cách hỏi/diễn đạt và không copy nguyên văn.']
    labels={'single_select':'MỘT ĐÁP ÁN','multi_select':'NHIỀU ĐÁP ÁN','text_input':'TRẢ LỜI NGẮN','numerical_input':'TRẢ LỜI SỐ'}
    for index, question in enumerate(questions, start=1):
        prefix='' if re.match(r'^(câu|question)\s*\d+',question.question,flags=re.IGNORECASE) else f'Câu {index}: '
        parts.append(f'{prefix}{question.question} [{labels.get(question.question_type, question.question_type)}]'.strip())
        if question.question_type in {'single_select','multi_select'}:
            for choice_index,choice in enumerate(question.choices):
                letter=chr(ord('A')+choice_index); marker=' [ĐÁP ÁN ĐÚNG]' if choice.correct else ''
                parts.append(f'{letter}. {choice.text}{marker}')
        elif question.question_type=='text_input':
            for answer in question.accepted_answers: parts.append(f'[ĐÁP ÁN CHẤP NHẬN] {answer}')
            parts.append('Phân biệt hoa/thường: '+('Có' if question.case_sensitive else 'Không'))
        elif question.question_type=='numerical_input':
            parts.append(f'[ĐÁP ÁN SỐ] {question.numerical_answer or ""}')
            parts.append(f'[SAI SỐ] {question.numerical_tolerance}{"%" if question.numerical_tolerance_type=="percent" else ""}')
        if question.solution: parts.append(f'Giải thích: {question.solution}')
        for warning in question.warnings: parts.append(f'[CẢNH BÁO PARSER] {warning}')
    return '\n'.join(parts).strip()

