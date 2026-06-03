from __future__ import annotations

from html import escape
from xml.etree import ElementTree as ET

from app.models.question import Question


ANSWER_FIELD_TO_LABEL = {
    'A': 'option_a',
    'B': 'option_b',
    'C': 'option_c',
    'D': 'option_d',
}


def _safe_text(value: object) -> str:
    return escape(str(value or ''), quote=True)


def _compact_text(value: object, max_len: int = 80) -> str:
    text = ' '.join(str(value or '').split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + '…'


def _build_problem_display_name(question: Question) -> str:
    """Use the former OLX description/learning objective as the card title.

    Open edX shows <description> directly under the prompt in LMS. That makes
    each one-question problem look noisy. Keep the useful description text, but
    move it into display_name so Library/Problem Bank cards remain meaningful
    while the learner view stays compact.
    """
    for candidate in (
        question.learning_objective,
        question.topic,
        question.source_node_title,
        question.question_text,
    ):
        title = _compact_text(candidate, 90)
        if title:
            return title
    return _compact_text(f"Learning Check - {question.id[:8]}", 90)


def _build_hint_text(question: Question) -> str:
    """Build a non-answer-revealing Open edX hint for the exported problem.

    Do not reuse the explanation as a hint because explanation often reveals the
    correct answer. The hint should only point the learner back to the relevant
    concept/source.
    """
    objective = str(question.learning_objective or '').strip()
    topic = str(question.topic or '').strip()
    chapter = str(question.chapter_title or '').strip()
    source_type = str(question.source_type or '').strip()
    if objective:
        return f'Gợi ý: Xem lại mục tiêu/khái niệm: {objective}'
    if chapter:
        return f'Gợi ý: Xem lại nội dung trong {chapter} và xác định ý chính trước khi chọn đáp án.'
    if topic:
        return f'Gợi ý: Tập trung vào khái niệm liên quan đến {topic} trong học liệu.'
    if source_type:
        return f'Gợi ý: Xem lại phần học liệu nguồn loại {source_type} liên quan đến câu hỏi này.'
    return 'Gợi ý: Đọc lại phần học liệu liên quan và loại trừ các đáp án không đúng với khái niệm chính.'


def validate_question_for_olx(question: Question) -> None:
    """Validate the last mile before exporting a question to CMS OLX.

    Quality checker already catches most model errors, but the exporter is the
    final guard before data leaves AI Server. It should never produce a broken
    or ambiguous OLX problem.
    """
    errors: list[str] = []
    if question.question_type != 'single_choice':
        errors.append('Only single_choice questions are supported by this exporter.')
    if question.correct_answer not in ANSWER_FIELD_TO_LABEL:
        errors.append('correct_answer must be one of A/B/C/D.')
    if not (question.question_text or '').strip():
        errors.append('question_text is required.')
    options = [getattr(question, field, '') for field in ANSWER_FIELD_TO_LABEL.values()]
    if any(not str(option or '').strip() for option in options):
        errors.append('All four options A/B/C/D are required.')
    normalized_options = [str(option or '').strip().lower() for option in options]
    if len(set(normalized_options)) != len(normalized_options):
        errors.append('Options A/B/C/D must not be duplicated.')
    if errors:
        raise ValueError(' '.join(errors))


def question_to_internal_json(question: Question) -> dict:
    """Return the AI Server canonical question JSON.

    This format is designed for review/versioning/cost/source tracking. It is not
    the final CMS import format. Use question_to_openedx_olx for export.
    """
    return {
        'id': question.id,
        'course_id': question.course_id,
        'lesson_id': question.lesson_id,
        'lesson_title': question.lesson_title,
        'block_id': question.block_id,
        'topic': question.topic,
        'difficulty': question.difficulty,
        'cognitive_level': question.cognitive_level,
        'learning_objective': question.learning_objective,
        'question_type': question.question_type,
        'question_text': question.question_text,
        'options': {
            'A': question.option_a,
            'B': question.option_b,
            'C': question.option_c,
            'D': question.option_d,
        },
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
        },
        'tags': question.tags or [],
        'quality': {
            'score': question.quality_score,
            'flags': question.quality_flags or [],
            'is_duplicate': question.is_duplicate,
            'duplicate_of_question_id': question.duplicate_of_question_id,
        },
        'status': question.status,
        'version': question.version,
    }


def question_to_openedx_olx(question: Question, include_source_in_solution: bool = False) -> str:
    """Convert one reviewed single-choice question to CMS OLX XML.

    Source/chapter/library metadata and CMS tags are intentionally **not** embedded
    inside the <problem> XML. They are sent separately through the connector
    metadata payload so Studio/Library import stays compatible with OLX parsers.
    """
    validate_question_for_olx(question)

    display_name = _safe_text(_build_problem_display_name(question))
    prompt = _safe_text(question.question_text)
    explanation = _safe_text(question.explanation)
    hint = _safe_text(_build_hint_text(question))
    source_ref = _safe_text(question.source_ref)
    source_excerpt = _safe_text(question.source_excerpt)

    choices = []
    for label in ['A', 'B', 'C', 'D']:
        field_name = ANSWER_FIELD_TO_LABEL[label]
        text = _safe_text(getattr(question, field_name))
        is_correct = 'true' if label == question.correct_answer else 'false'
        choices.append(f'      <choice correct="{is_correct}">{text}</choice>')

    source_xml = ''
    if include_source_in_solution and (source_ref or source_excerpt):
        source_xml = f'''
        <p><strong>Nguồn:</strong> {source_ref}</p>
        <p>{source_excerpt}</p>'''

    choices_xml = '\n'.join(choices)
    xml = f'''<problem display_name="{display_name}">
  <multiplechoiceresponse>
    <label>{prompt}</label>
    <choicegroup type="MultipleChoice">
{choices_xml}
    </choicegroup>
    <solution>
      <div class="detailed-solution">
        <p>{explanation}</p>{source_xml}
      </div>
    </solution>
  </multiplechoiceresponse>
  <demandhint>
    <hint>{hint}</hint>
  </demandhint>
</problem>'''
    # Last-mile XML well-formedness check. ElementTree also catches accidental
    # unescaped characters if future changes bypass _safe_text.
    ET.fromstring(xml)
    return xml


def questions_to_openedx_olx_fragment(questions: list[Question]) -> str:
    """Return an OLX fragment containing multiple independent <problem> blocks.

    This is for human preview/download only. Production import should call the
    connector per problem or create a zip package with one XML file per problem.
    """
    return '\n\n'.join(question_to_openedx_olx(q) for q in questions)


def questions_to_openedx_olx_package(questions: list[Question]) -> str:
    """Backward-compatible alias for existing export endpoint.

    Kept to avoid breaking callers, but the return value is a preview fragment,
    not a full OLX package with a single XML root.
    """
    return questions_to_openedx_olx_fragment(questions)
