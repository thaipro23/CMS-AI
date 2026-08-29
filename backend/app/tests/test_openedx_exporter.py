from xml.etree import ElementTree as ET

import pytest

from app.models.question import Question
from app.services.cms_tags import build_question_tags
from app.services.openedx_exporter import question_to_openedx_olx


class DummyTarget:
    source_node_id = 'course-v1:TEST+AI+2026+type@vertical+block@unit-http-methods'
    source_node_title = 'Unit 1.2: GET POST PUT DELETE'
    chapter_node_id = 'course-v1:TEST+AI+2026+type@chapter+block@chapter-rest-api'
    chapter_title = 'Chương 1: REST API cơ bản'
    difficulty = 'easy'


def make_question(**overrides):
    data = dict(
        id='12345678-0000-0000-0000-000000000000',
        course_id='course-v1:TEST+AI+2026',
        topic='HTTP Methods',
        concept_title='HTTP GET',
        difficulty='easy',
        cognitive_level='understand',
        question_type='single_choice',
        question_text='GET dùng để làm gì?',
        option_a='Lấy dữ liệu',
        option_b='Xóa dữ liệu',
        option_c='Deploy ứng dụng',
        option_d='Thiết kế giao diện',
        correct_answer='A',
        explanation='GET dùng để lấy dữ liệu.',
        learning_objective='Phân biệt chức năng HTTP GET.',
        pedagogy_json={
            'hint': 'GET thuộc nhóm phương thức safe — thao tác này không nhằm làm thay đổi trạng thái tài nguyên trên server.',
            'misconceptions': {
                'A': '',
                'B': 'nhầm thao tác đọc với thao tác xóa',
                'C': 'nhầm HTTP method với quy trình triển khai',
                'D': 'nhầm giao thức dữ liệu với thiết kế giao diện',
            },
        },
        source_ref='slide:1',
        source_type='transcript',
        source_node_id=DummyTarget.source_node_id,
        source_node_title=DummyTarget.source_node_title,
        status='approved',
        tags=['HTTP Methods'],
    )
    data.update(overrides)
    return Question(**data)


def test_question_to_olx_contains_multiple_choice():
    xml = question_to_openedx_olx(make_question())
    root = ET.fromstring(xml)
    assert root.tag == 'problem'
    assert root.find('.//multiplechoiceresponse') is not None
    assert 'correct="true"' in xml


def test_exporter_emits_one_friendly_indirect_knowledge_hint():
    xml = question_to_openedx_olx(make_question())
    root = ET.fromstring(xml)
    hints = [node.text or '' for node in root.findall('.//demandhint/hint')]
    assert len(hints) == 1
    assert hints[0] == (
        'Gợi ý nhỏ: GET thuộc nhóm phương thức safe — thao tác này không nhằm làm thay đổi '
        'trạng thái tài nguyên trên server.'
    )
    # Knowledge clue, not test-taking guidance and not a direct answer restatement.
    lowered = hints[0].lower()
    assert 'hãy so sánh' not in lowered
    assert 'loại phương án' not in lowered
    assert 'đáp án đúng' not in lowered
    assert 'lấy dữ liệu' not in lowered


def test_exporter_emits_misconception_specific_choice_feedback():
    root = ET.fromstring(question_to_openedx_olx(make_question()))
    choices = root.findall('.//choicegroup/choice')
    assert len(choices) == 4
    feedback = [(choice.findtext('choicehint') or '') for choice in choices]
    assert feedback[0].startswith('Đúng.')
    assert 'nhầm thao tác đọc với thao tác xóa' in feedback[1]
    assert 'nhầm HTTP method với quy trình triển khai' in feedback[2]
    assert 'nhầm giao thức dữ liệu với thiết kế giao diện' in feedback[3]


def test_hint_sanitizer_rejects_explicit_answer_label():
    q = make_question(pedagogy_json={
        'hint': 'Đáp án đúng là A: Lấy dữ liệu',
        'misconceptions': {'A': '', 'B': 'nhầm xóa', 'C': 'nhầm deploy', 'D': 'nhầm UI'},
    })
    root = ET.fromstring(question_to_openedx_olx(q))
    assert root.findall('.//demandhint/hint') == []


def test_hint_sanitizer_rejects_near_verbatim_correct_option():
    q = make_question(
        option_a='Truy xuất dữ liệu từ tài nguyên',
        pedagogy_json={
            'hint': 'Truy xuất dữ liệu từ tài nguyên là chức năng đang được nhắc tới.',
            'misconceptions': {'A': '', 'B': 'nhầm xóa', 'C': 'nhầm deploy', 'D': 'nhầm UI'},
        },
    )
    root = ET.fromstring(question_to_openedx_olx(q))
    assert root.findall('.//demandhint/hint') == []


def test_exporter_hint_never_reuses_explanation_or_source_evidence():
    secret_explanation = 'Đáp án đúng là A vì GET dùng để lấy dữ liệu.'
    xml = question_to_openedx_olx(make_question(
        explanation=secret_explanation,
        source_evidence='GET được dùng để lấy dữ liệu từ server.',
        source_excerpt='GET đọc tài nguyên.',
        pedagogy_json={'misconceptions': {'A': '', 'B': 'nhầm xóa', 'C': 'nhầm deploy', 'D': 'nhầm UI'}},
    ))
    root = ET.fromstring(xml)
    assert root.findall('.//demandhint/hint') == []


def test_legacy_question_may_use_old_clue_if_it_passes_leak_guard():
    root = ET.fromstring(question_to_openedx_olx(make_question(
        pedagogy_json={
            'clue': 'GET thuộc nhóm phương thức safe và không nhằm thay đổi trạng thái tài nguyên.',
            'misconceptions': {'A': '', 'B': 'nhầm xóa', 'C': 'nhầm deploy', 'D': 'nhầm UI'},
        },
        source_evidence='GET được dùng để lấy dữ liệu.',
    )))
    hints = [node.text or '' for node in root.findall('.//demandhint/hint')]
    assert hints == ['Gợi ý nhỏ: GET thuộc nhóm phương thức safe và không nhằm thay đổi trạng thái tài nguyên.']
    feedback = root.findall('.//choicehint')
    assert len(feedback) == 4


def test_question_without_knowledge_does_not_show_useless_instruction_hint():
    root = ET.fromstring(question_to_openedx_olx(make_question(
        pedagogy_json={}, source_evidence='GET được dùng để lấy dữ liệu.', source_excerpt='GET đọc tài nguyên.'
    )))
    assert root.findall('.//demandhint/hint') == []


def test_olx_does_not_embed_internal_metadata():
    xml = question_to_openedx_olx(make_question())
    assert '<metadata>' not in xml
    assert 'source_node_id' not in xml
    assert 'target_library_key' not in xml
    assert 'pedagogy_json' not in xml


def test_exporter_uses_learning_objective_as_display_name_and_omits_description():
    xml = question_to_openedx_olx(make_question())
    root = ET.fromstring(xml)
    assert root.attrib['display_name'] == 'Phân biệt chức năng HTTP GET.'
    assert root.find('.//description') is None
    assert '<description>' not in xml


def test_exporter_rejects_invalid_question_before_cms_import():
    with pytest.raises(ValueError):
        question_to_openedx_olx(make_question(option_b='Lấy dữ liệu'))


def test_question_tags_include_filterable_cms_tags():
    payload = build_question_tags(make_question(), DummyTarget())
    assert 'ai-learning-check' in payload.tag_names
    assert 'difficulty:EASY' in payload.tag_names
    assert any(tag.startswith('family:') for tag in payload.tag_names)
    assert any(tag.startswith('chapter:') for tag in payload.tag_names)
