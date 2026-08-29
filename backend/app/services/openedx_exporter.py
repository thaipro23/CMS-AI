from __future__ import annotations

from html import escape
import re
from typing import Iterable
from xml.etree import ElementTree as ET

from app.models.question import Question, QuestionMedia
from app.services.pedagogy import build_choice_feedback, build_hint_texts
from app.services.question_content import canonical_question_content, normalize_question_content, normalize_question_type

ANSWER_FIELD_TO_LABEL = {'A': 'option_a', 'B': 'option_b', 'C': 'option_c', 'D': 'option_d'}
MEDIA_PLACEHOLDER_PREFIX = '__ACMS_MEDIA_'
BLANK_TOKEN_RE = re.compile(r'\[_{3,}\]')


def media_placeholder(media_id: str) -> str:
    return f'{MEDIA_PLACEHOLDER_PREFIX}{media_id}__'


def _safe_text(value: object) -> str:
    return escape(str(value or ''), quote=True)


def _compact_text(value: object, max_len: int = 80) -> str:
    text = ' '.join(str(value or '').split())
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + '…'


def _build_problem_display_name(question: Question) -> str:
    for candidate in (question.learning_objective, question.topic, question.source_node_title, question.question_text):
        title = _compact_text(candidate, 90)
        if title:
            return title
    return _compact_text(f'Learning Check - {question.id[:8]}', 90)


def _validated_content(question: Question) -> dict:
    raw = canonical_question_content(question)
    return normalize_question_content(normalize_question_type(question.question_type), raw)


def validate_question_for_olx(question: Question) -> None:
    errors: list[str] = []
    if not str(question.question_text or '').strip():
        errors.append('question_text is required.')
    try:
        content = _validated_content(question)
        if content['response']['type'] == 'dropdown_fill':
            blank_count = len(BLANK_TOKEN_RE.findall(str(question.question_text or '')))
            answer_count = len(content['response']['correct_option_ids'])
            if blank_count != answer_count:
                errors.append(
                    f'Số ô trống ({blank_count}) phải bằng số đáp án đúng theo thứ tự ({answer_count}).'
                )
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        raise ValueError(' '.join(errors))


def question_to_internal_json(question: Question) -> dict:
    return {
        'id': question.id,
        'course_id': question.course_id,
        'lesson_id': question.lesson_id,
        'lesson_title': question.lesson_title,
        'block_id': question.block_id,
        'topic': question.topic,
        'difficulty': question.difficulty,
        'question_family_id': question.question_family_id,
        'variant_no': question.variant_no,
        'cognitive_level': question.cognitive_level,
        'learning_objective': question.learning_objective,
        'pedagogy': question.pedagogy_json or {},
        'question_schema_version': int(getattr(question, 'question_schema_version', 1) or 1),
        'authoring_mode': str(getattr(question, 'authoring_mode', '') or 'ai'),
        'question_type': normalize_question_type(question.question_type),
        'question_text': question.question_text,
        'question_content': canonical_question_content(question),
        'options': {'A': question.option_a, 'B': question.option_b, 'C': question.option_c, 'D': question.option_d},
        'correct_answer': question.correct_answer,
        'explanation': question.explanation,
        'source': {
            'ref': question.source_ref,
            'type': question.source_type,
            'page': question.source_page,
            'timestamp_start': question.source_timestamp_start,
            'timestamp_end': question.source_timestamp_end,
            'chunk_id': question.source_chunk_id,
            'source_node_id': question.source_node_id,
            'source_node_title': question.source_node_title,
            'chapter_node_id': question.chapter_node_id,
            'chapter_title': question.chapter_title,
            'target_library_key': question.target_library_key,
            'excerpt': question.source_excerpt,
            'evidence': question.source_evidence,
        },
        'tags': question.tags or [],
        'quality': {
            'score': question.quality_score,
            'flags': question.quality_flags or [],
            'is_duplicate': question.is_duplicate,
            'family_id': question.question_family_id,
            'variant_no': question.variant_no,
            'duplicate_of_question_id': question.duplicate_of_question_id,
        },
        'status': question.status,
        'version': question.version,
    }


def _media_html(media: Iterable[QuestionMedia] | None) -> str:
    items = sorted(list(media or []), key=lambda item: (int(item.sort_order or 0), str(item.id)))
    if not items:
        return ''
    parts = []
    for item in items:
        alt = _safe_text(item.alt_text)
        src = _safe_text(media_placeholder(str(item.id)))
        parts.append(f'    <p><img src="{src}" alt="{alt}" /></p>')
    return '\n'.join(parts) + '\n'


def _solution_xml(question: Question, *, include_source_in_solution: bool) -> str:
    explanation = _safe_text(question.explanation)
    source_xml = ''
    if include_source_in_solution and (question.source_ref or question.source_excerpt):
        source_xml = (
            f'\n        <p><strong>Nguồn:</strong> {_safe_text(question.source_ref)}</p>'
            f'\n        <p>{_safe_text(question.source_excerpt)}</p>'
        )
    return f'''    <solution>\n      <div class="detailed-solution">\n        <p>{explanation}</p>{source_xml}\n      </div>\n    </solution>'''


def _hints_xml(question: Question) -> str:
    hints = [_safe_text(item) for item in build_hint_texts(question)]
    if not hints:
        return ''
    body = '\n'.join(f'    <hint>{item}</hint>' for item in hints)
    return f'  <demandhint>\n{body}\n  </demandhint>\n'


def question_to_openedx_olx(
    question: Question,
    include_source_in_solution: bool = False,
    *,
    media: Iterable[QuestionMedia] | None = None,
) -> str:
    """Export supported canonical responses to native Open edX OLX.

    Media references use placeholders. The connector uploads each image as a
    Content Library static asset and replaces the placeholder before setting OLX.
    """
    validate_question_for_olx(question)
    content = _validated_content(question)
    response = content['response']
    qtype = response['type']
    display_name = _safe_text(_build_problem_display_name(question))
    prompt = _safe_text(question.question_text)
    media_xml = _media_html(media)
    solution_xml = _solution_xml(question, include_source_in_solution=include_source_in_solution)
    hints_xml = _hints_xml(question)

    if qtype == 'single_select':
        choices = []
        for index, option in enumerate(response['options']):
            is_correct = 'true' if option['correct'] else 'false'
            explicit_feedback = str(option.get('feedback') or '').strip()
            fallback_feedback = ''
            if not explicit_feedback and index < 4:
                fallback_feedback = build_choice_feedback(question, chr(ord('A') + index))
            feedback = _safe_text(explicit_feedback or fallback_feedback)
            hint = f'<choicehint>{feedback}</choicehint>' if feedback else ''
            choices.append(f'      <choice correct="{is_correct}">{_safe_text(option["text"])}{hint}</choice>')
        response_xml = f'''  <multiplechoiceresponse>\n    <label>{prompt}</label>\n{media_xml}    <choicegroup type="MultipleChoice">\n{chr(10).join(choices)}\n    </choicegroup>\n{solution_xml}\n  </multiplechoiceresponse>'''
    elif qtype == 'multi_select':
        choices = []
        for option in response['options']:
            is_correct = 'true' if option['correct'] else 'false'
            feedback = _safe_text(option.get('feedback'))
            hint = f'<choicehint>{feedback}</choicehint>' if feedback else ''
            choices.append(f'      <choice correct="{is_correct}">{_safe_text(option["text"])}{hint}</choice>')
        response_xml = f'''  <choiceresponse>\n    <label>{prompt}</label>\n{media_xml}    <checkboxgroup>\n{chr(10).join(choices)}\n    </checkboxgroup>\n{solution_xml}\n  </choiceresponse>'''
    elif qtype == 'dropdown_fill':
        raw_segments = BLANK_TOKEN_RE.split(str(question.question_text or ''))
        inline_parts = [_safe_text(raw_segments[0])]
        for blank_index, correct_id in enumerate(response['correct_option_ids']):
            choices = []
            for option in response['options']:
                is_correct = 'true' if option['id'] == correct_id else 'false'
                choices.append(
                    f'          <option correct="{is_correct}">{_safe_text(option["text"])}</option>'
                )
            inline_solution = (
                f'\n{solution_xml}'
                if blank_index == len(response['correct_option_ids']) - 1
                else ''
            )
            inline_parts.append(
                '      <optionresponse inline="1">\n'
                f'        <label>Ô trống {blank_index + 1}</label>\n'
                '        <optioninput inline="1">\n'
                f'{chr(10).join(choices)}\n'
                '        </optioninput>\n'
                f'{inline_solution}\n'
                '      </optionresponse>'
            )
            inline_parts.append(_safe_text(raw_segments[blank_index + 1]))
        response_text = ''.join(inline_parts)
        response_xml = (
            '  <div class="acms-dropdown-fill">\n'
            f'    <p>{response_text}</p>\n'
            f'{media_xml}'
            '  </div>'
        )
    elif qtype == 'text_input':
        answers = response['accepted_answers']
        primary = _safe_text(answers[0]['text'])
        mode = 'cs' if response.get('case_sensitive') else 'ci'
        additional = '\n'.join(
            f'      <additional_answer answer="{_safe_text(item["text"])}" />'
            for item in answers[1:]
        )
        additional_xml = (additional + '\n') if additional else ''
        response_xml = f'''  <stringresponse answer="{primary}" type="{mode}">\n    <label>{prompt}</label>\n{media_xml}{additional_xml}    <textline size="40" />\n{solution_xml}\n  </stringresponse>'''
    else:
        answer = _safe_text(response['answer'])
        tolerance = _safe_text(response['tolerance'])
        if response.get('tolerance_type') == 'percent':
            tolerance = f'{tolerance}%'
        tolerance_xml = (
            f'    <responseparam type="tolerance" default="{tolerance}" />\n'
            if str(response.get('tolerance') or '0') != '0'
            else ''
        )
        response_xml = f'''  <numericalresponse answer="{answer}">\n    <label>{prompt}</label>\n{media_xml}{tolerance_xml}    <formulaequationinput />\n{solution_xml}\n  </numericalresponse>'''

    xml = f'''<problem display_name="{display_name}">\n{response_xml}\n{hints_xml}</problem>'''
    ET.fromstring(xml)
    return xml


def questions_to_openedx_olx_fragment(questions: list[Question]) -> str:
    return '\n\n'.join(question_to_openedx_olx(question) for question in questions)


def questions_to_openedx_olx_package(questions: list[Question]) -> str:
    return questions_to_openedx_olx_fragment(questions)
