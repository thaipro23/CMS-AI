from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.question import Question

QUESTION_SCHEMA_VERSION = 2
CANONICAL_QUESTION_TYPES = {
    'single_select',
    'multi_select',
    'dropdown_fill',
    'text_input',
    'numerical_input',
}
QUESTION_TYPE_ALIASES = {
    'single_choice': 'single_select',
    'multiple_choice': 'single_select',
    'multiplechoiceresponse': 'single_select',
    'single_select': 'single_select',
    'multi_choice': 'multi_select',
    'multiple_select': 'multi_select',
    'checkbox': 'multi_select',
    'choiceresponse': 'multi_select',
    'multi_select': 'multi_select',
    'dropdown': 'dropdown_fill',
    'dropdown_fill': 'dropdown_fill',
    'fill_blank_choice': 'dropdown_fill',
    'optionresponse': 'dropdown_fill',
    'text': 'text_input',
    'string': 'text_input',
    'stringresponse': 'text_input',
    'text_input': 'text_input',
    'numeric': 'numerical_input',
    'number': 'numerical_input',
    'numericalresponse': 'numerical_input',
    'numerical_input': 'numerical_input',
}


def normalize_question_type(value: object) -> str:
    raw = str(value or 'single_choice').strip().lower()
    normalized = QUESTION_TYPE_ALIASES.get(raw, raw)
    if normalized not in CANONICAL_QUESTION_TYPES:
        raise ValueError(f'Loại câu hỏi {raw!r} chưa được hỗ trợ.')
    return normalized


def _clean_text(value: object, *, required: bool = False, field: str = 'text', max_len: int | None = None) -> str:
    text = str(value or '').strip()
    if required and not text:
        raise ValueError(f'{field} không được để trống.')
    if max_len is not None and len(text) > max_len:
        raise ValueError(f'{field} vượt quá {max_len} ký tự.')
    return text


def _stable_option_id(value: object | None, *, index: int) -> str:
    raw = re.sub(r'[^a-zA-Z0-9_.:-]+', '-', str(value or '').strip()).strip('-')
    if raw:
        return raw[:80]
    return f'opt-{index + 1}-{uuid.uuid4().hex[:8]}'


def _normalize_options(options: object, *, require_multiple_correct: bool) -> list[dict[str, Any]]:
    if not isinstance(options, list):
        raise ValueError('Danh sách đáp án phải là một mảng.')
    if not (2 <= len(options) <= 12):
        raise ValueError('Câu lựa chọn phải có từ 2 đến 12 đáp án.')
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for index, item in enumerate(options):
        if not isinstance(item, dict):
            raise ValueError('Mỗi đáp án phải là một object.')
        option_id = _stable_option_id(item.get('id'), index=index)
        if option_id in seen_ids:
            raise ValueError('ID đáp án bị trùng.')
        text = _clean_text(item.get('text'), required=True, field='Nội dung đáp án', max_len=4000)
        normalized_text = ' '.join(text.casefold().split())
        if normalized_text in seen_texts:
            raise ValueError('Các đáp án không được trùng nội dung.')
        seen_ids.add(option_id)
        seen_texts.add(normalized_text)
        result.append({
            'id': option_id,
            'text': text,
            'correct': bool(item.get('correct')),
            'feedback': _clean_text(item.get('feedback'), max_len=4000),
        })
    correct_count = sum(1 for item in result if item['correct'])
    if require_multiple_correct:
        if correct_count < 2:
            raise ValueError('Câu nhiều đáp án phải có ít nhất 2 đáp án đúng.')
        if correct_count == len(result):
            raise ValueError('Câu nhiều đáp án phải có ít nhất 1 đáp án sai.')
    elif correct_count != 1:
        raise ValueError('Câu một đáp án phải có đúng 1 đáp án đúng.')
    return result


def _normalize_dropdown_fill(response: dict[str, Any]) -> dict[str, Any]:
    raw_options = response.get('options')
    if not isinstance(raw_options, list):
        raise ValueError('Danh sách đáp án phải là một mảng.')
    if not (2 <= len(raw_options) <= 12):
        raise ValueError('Câu điền ô trống phải có từ 2 đến 12 đáp án.')

    options: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for index, item in enumerate(raw_options):
        if not isinstance(item, dict):
            raise ValueError('Mỗi đáp án phải là một object.')
        option_id = _stable_option_id(item.get('id'), index=index)
        if option_id in seen_ids:
            raise ValueError('ID đáp án bị trùng.')
        option_text = _clean_text(
            item.get('text'),
            required=True,
            field='Nội dung đáp án',
            max_len=4000,
        )
        normalized_text = ' '.join(option_text.casefold().split())
        if normalized_text in seen_texts:
            raise ValueError('Các đáp án không được trùng nội dung.')
        seen_ids.add(option_id)
        seen_texts.add(normalized_text)
        options.append({
            'id': option_id,
            'text': option_text,
            'correct': False,
            'feedback': _clean_text(item.get('feedback'), max_len=4000),
        })

    raw_correct_ids = response.get('correct_option_ids')
    if not isinstance(raw_correct_ids, list) or not raw_correct_ids:
        raise ValueError('Câu điền ô trống phải có ít nhất 1 đáp án đúng theo thứ tự.')
    if len(raw_correct_ids) > 10:
        raise ValueError('Câu điền ô trống hỗ trợ tối đa 10 ô trống.')
    correct_option_ids = [str(item or '').strip() for item in raw_correct_ids]
    if any(not item for item in correct_option_ids):
        raise ValueError('ID đáp án đúng cho ô trống không hợp lệ.')
    known_ids = {item['id'] for item in options}
    unknown_ids = sorted({item for item in correct_option_ids if item not in known_ids})
    if unknown_ids:
        raise ValueError(f'Đáp án đúng tham chiếu ID không tồn tại: {", ".join(unknown_ids)}.')

    selected_ids = set(correct_option_ids)
    for option in options:
        option['correct'] = option['id'] in selected_ids
    return {'options': options, 'correct_option_ids': correct_option_ids}


def normalize_question_content(question_type: object, content: object) -> dict[str, Any]:
    qtype = normalize_question_type(question_type)
    payload = deepcopy(content) if isinstance(content, dict) else {}
    response = payload.get('response') if isinstance(payload.get('response'), dict) else payload
    response_type = normalize_question_type(response.get('type') or qtype)
    if response_type != qtype:
        raise ValueError('question_type và response.type không khớp nhau.')

    normalized_response: dict[str, Any] = {'type': qtype}
    if qtype in {'single_select', 'multi_select'}:
        normalized_response['options'] = _normalize_options(
            response.get('options'),
            require_multiple_correct=qtype == 'multi_select',
        )
    elif qtype == 'dropdown_fill':
        normalized_response.update(_normalize_dropdown_fill(response))
    elif qtype == 'text_input':
        answers = response.get('accepted_answers')
        if not isinstance(answers, list) or not answers:
            raise ValueError('Câu trả lời ngắn phải có ít nhất 1 đáp án chấp nhận.')
        normalized_answers: list[dict[str, Any]] = []
        seen: set[tuple[str, bool]] = set()
        for raw_item in answers[:20]:
            item = {'text': raw_item, 'case_sensitive': False} if isinstance(raw_item, str) else raw_item
            if not isinstance(item, dict):
                raise ValueError('Đáp án text không hợp lệ.')
            text = _clean_text(item.get('text'), required=True, field='Đáp án text', max_len=1000)
            case_sensitive = bool(item.get('case_sensitive'))
            key = (text if case_sensitive else text.casefold(), case_sensitive)
            if key in seen:
                continue
            seen.add(key)
            normalized_answers.append({'text': text, 'case_sensitive': case_sensitive})
        if not normalized_answers:
            raise ValueError('Câu trả lời ngắn phải có đáp án hợp lệ.')
        modes = {item['case_sensitive'] for item in normalized_answers}
        if len(modes) > 1:
            raise ValueError('Các đáp án text trong cùng câu phải dùng cùng chế độ phân biệt hoa/thường.')
        normalized_response['accepted_answers'] = normalized_answers
        normalized_response['case_sensitive'] = bool(normalized_answers[0]['case_sensitive'])
    else:
        raw_answer = response.get('answer')
        try:
            answer = Decimal(str(raw_answer).strip())
        except (InvalidOperation, AttributeError):
            raise ValueError('Đáp án số không hợp lệ.') from None
        raw_tolerance = response.get('tolerance', 0)
        try:
            tolerance = Decimal(str(raw_tolerance).strip())
        except (InvalidOperation, AttributeError):
            raise ValueError('Sai số cho phép không hợp lệ.') from None
        if tolerance < 0:
            raise ValueError('Sai số cho phép không được âm.')
        tolerance_type = str(response.get('tolerance_type') or 'absolute').strip().lower()
        if tolerance_type not in {'absolute', 'percent'}:
            raise ValueError('tolerance_type chỉ hỗ trợ absolute hoặc percent.')
        normalized_response.update({
            'answer': format(answer, 'f'),
            'tolerance': format(tolerance, 'f'),
            'tolerance_type': tolerance_type,
        })

    return {'schema_version': QUESTION_SCHEMA_VERSION, 'response': normalized_response}


def content_from_legacy_question(question: 'Question') -> dict[str, Any]:
    qtype = normalize_question_type(getattr(question, 'question_type', None))
    if qtype in {'single_select', 'multi_select', 'dropdown_fill'}:
        labels = ('A', 'B', 'C', 'D')
        values = (
            getattr(question, 'option_a', ''), getattr(question, 'option_b', ''),
            getattr(question, 'option_c', ''), getattr(question, 'option_d', ''),
        )
        correct_legacy = {
            part.strip().upper()
            for part in str(getattr(question, 'correct_answer', '') or '').split(',')
            if part.strip()
        }
        if qtype in {'single_select', 'dropdown_fill'} and not correct_legacy:
            correct_legacy = {'A'}
        options = [
            {'id': f'legacy-{label.lower()}', 'text': str(text or ''), 'correct': label in correct_legacy, 'feedback': ''}
            for label, text in zip(labels, values)
            if str(text or '').strip()
        ]
        response: dict[str, Any] = {'type': qtype, 'options': options}
        if qtype == 'dropdown_fill':
            correct_id = next((item['id'] for item in options if item['correct']), options[0]['id'] if options else '')
            response['correct_option_ids'] = [correct_id] if correct_id else []
        return {'schema_version': 1, 'response': response}
    if qtype == 'text_input':
        answer = str(getattr(question, 'option_a', '') or '').strip()
        return {
            'schema_version': 1,
            'response': {
                'type': qtype,
                'accepted_answers': [{'text': answer, 'case_sensitive': False}] if answer else [],
                'case_sensitive': False,
            },
        }
    return {
        'schema_version': 1,
        'response': {
            'type': qtype,
            'answer': str(getattr(question, 'option_a', '') or '').strip(),
            'tolerance': '0',
            'tolerance_type': 'absolute',
        },
    }


def canonical_question_content(question: 'Question', *, validate: bool = False) -> dict[str, Any]:
    raw = getattr(question, 'question_content_json', None)
    raw = raw if isinstance(raw, dict) else None
    if raw:
        response = raw.get('response') if isinstance(raw.get('response'), dict) else {}
        qtype = response.get('type') or getattr(question, 'question_type', None)
        return normalize_question_content(qtype, raw) if validate else deepcopy(raw)
    legacy = content_from_legacy_question(question)
    return normalize_question_content(legacy['response']['type'], legacy) if validate else legacy


def apply_canonical_content(question: 'Question', question_type: object, content: object) -> dict[str, Any]:
    normalized = normalize_question_content(question_type, content)
    qtype = normalized['response']['type']
    setattr(question, 'question_schema_version', QUESTION_SCHEMA_VERSION)
    setattr(question, 'question_type', qtype)
    setattr(question, 'question_content_json', normalized)

    # Compatibility mirrors only. Canonical JSON is authoritative for new types.
    for field in ('option_a', 'option_b', 'option_c', 'option_d'):
        setattr(question, field, '')
    setattr(question, 'correct_answer', 'A')
    if qtype in {'single_select', 'multi_select'}:
        options = normalized['response']['options']
        labels = ('A', 'B', 'C', 'D')
        correct_labels: list[str] = []
        for index, option in enumerate(options[:4]):
            setattr(question, f'option_{labels[index].lower()}', option['text'])
            if option['correct']:
                correct_labels.append(labels[index])
        setattr(question, 'correct_answer', (correct_labels or ['A'])[0])
    elif qtype == 'dropdown_fill':
        options = normalized['response']['options']
        labels = ('A', 'B', 'C', 'D')
        id_to_label: dict[str, str] = {}
        for index, option in enumerate(options[:4]):
            label = labels[index]
            id_to_label[option['id']] = label
            setattr(question, f'option_{label.lower()}', option['text'])
        first_correct_id = normalized['response']['correct_option_ids'][0]
        setattr(question, 'correct_answer', id_to_label.get(first_correct_id, 'A'))
    elif qtype == 'text_input':
        setattr(question, 'option_a', normalized['response']['accepted_answers'][0]['text'])
    else:
        setattr(question, 'option_a', normalized['response']['answer'])
    return normalized


def question_response_fingerprint(question: 'Question') -> str:
    payload = {
        'question_text': ' '.join(str(getattr(question, 'question_text', '') or '').split()),
        'content': canonical_question_content(question),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def question_type_label(value: object) -> str:
    return {
        'single_select': 'Một đáp án',
        'multi_select': 'Nhiều đáp án',
        'dropdown_fill': 'Chọn và điền ô trống',
        'text_input': 'Trả lời ngắn',
        'numerical_input': 'Trả lời số',
    }[normalize_question_type(value)]
