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
        difficulty='easy',
        question_type='single_choice',
        question_text='GET dùng để làm gì?',
        option_a='Lấy dữ liệu',
        option_b='Xóa dữ liệu',
        option_c='Deploy',
        option_d='Thiết kế UI',
        correct_answer='A',
        explanation='GET dùng để lấy dữ liệu.',
        learning_objective='Nhận biết HTTP GET.',
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


def test_olx_does_not_embed_internal_metadata():
    xml = question_to_openedx_olx(make_question())
    assert '<metadata>' not in xml
    assert 'source_node_id' not in xml
    assert 'target_library_key' not in xml




def test_exporter_uses_learning_objective_as_display_name_and_omits_description():
    xml = question_to_openedx_olx(make_question())
    root = ET.fromstring(xml)
    assert root.attrib['display_name'] == 'Nhận biết HTTP GET.'
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
