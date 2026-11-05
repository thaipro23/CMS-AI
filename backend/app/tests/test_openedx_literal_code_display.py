"""Regressions for WEB3023 Quiz 01 row 119 and CAPA's XML-to-HTML boundary."""
from lxml import etree, html
import pytest

from app.models.question import QuestionMedia
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.question_content import apply_canonical_content
from app.tests.test_openedx_exporter import make_question


def _capa_html(node):
    # Ulmo xmodule/stringify.py stringify_children: initial text is raw; child
    # elements are XML-serialized, then the result is rendered as HTML by CAPA.
    return (node.text or '') + ''.join(etree.tostring(c, encoding='unicode') for c in node)


def _visible(node):
    return html.fragment_fromstring(_capa_html(node), create_parent='div')


@pytest.mark.parametrize('qtype', ['single_select', 'multi_select'])
def test_web3023_html_tag_options_render_as_literal_text(qtype):
    options = ['<time>', '<main>', '<details>', '<section>']
    question = make_question(question_type=qtype, authoring_mode='import', source_type='legacy_quiz_excel',
                             question_text='Thẻ nào định nghĩa phần nội dung chính của tài liệu HTML', pedagogy_json={})
    apply_canonical_content(question, qtype, {'response': {'options': [
        {'id': str(i), 'text': value, 'correct': i == 1 or (qtype == 'multi_select' and i == 3)}
        for i, value in enumerate(options)
    ]}})
    root = etree.fromstring(question_to_openedx_olx(question).encode())
    for choice, expected in zip(root.findall('.//choice'), options):
        # Feedback is a separate CAPA UI element, not answer text.
        for hint in choice.findall('choicehint'):
            choice.remove(hint)
        rendered = _visible(choice)
        assert rendered.text_content() == expected
        assert not rendered.xpath('.//time | .//main | .//details | .//section')
    assert [c.get('correct') for c in root.findall('.//choice')] == (
        ['false', 'true', 'false', 'true'] if qtype == 'multi_select' else ['false', 'true', 'false', 'false'])


@pytest.mark.parametrize('value', [
    '<!doctype html>', '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
    '<script>alert("hello")</script>', '<img src=x onerror=alert(1)>',
    '&lt;main&gt; &copy; &#60; & 3 < 4 > 2', '<p>Text</p><br/>',
])
def test_prompt_code_survives_xml_then_html_without_becoming_markup(value):
    question = make_question(question_text=f'Đoạn mã: {value}', authoring_mode='import', source_type='legacy_quiz_excel')
    root = etree.fromstring(question_to_openedx_olx(question).encode())
    rendered = _visible(root.find('.//label'))
    assert rendered.text_content() == f'Đoạn mã: {value}'
    assert not rendered.xpath('.//script | .//img | .//meta | .//main | .//br')
    assert root.get('display_name').startswith(f'Câu hỏi: Đoạn mã: {value}'[:50])


def test_choice_feedback_and_solution_keep_literal_code():
    question = make_question(explanation='Dùng <main> & không dùng <details>.', pedagogy_json={})
    apply_canonical_content(question, 'single_select', {'response': {'options': [
        {'id': 'a', 'text': 'A', 'correct': True, 'feedback': 'Xem <main> & <details>.'},
        {'id': 'b', 'text': 'B', 'correct': False, 'feedback': ''},
    ]}})
    root = etree.fromstring(question_to_openedx_olx(question).encode())
    assert _visible(root.find('.//choicehint')).text_content() == 'Xem <main> & <details>.'
    assert _visible(root.find('.//solution/div/p')).text_content() == 'Dùng <main> & không dùng <details>.'


def test_dropdown_options_and_text_input_answer_remain_plain_grading_values():
    dropdown = make_question(question_type='dropdown_fill', question_text='Thẻ <body>: [_____].')
    apply_canonical_content(dropdown, 'dropdown_fill', {'response': {
        'options': [{'id': 'main', 'text': '<main>'}, {'id': 'details', 'text': '<details>'}],
        'correct_option_ids': ['main'],
    }})
    root = etree.fromstring(question_to_openedx_olx(dropdown).encode())
    assert root.find('.//option[@correct="true"]').text == '<main>'
    assert len(root.find('.//option[@correct="true"]')) == 0
    paragraph = root.find('.//div[@class="acms-dropdown-fill"]/p')
    for response in paragraph.findall('optionresponse'):
        paragraph.remove(response)
    assert _visible(paragraph).text_content().startswith('Thẻ <body>: ')
    text = make_question(question_type='text_input', question_text='Nhập thẻ <main>.')
    apply_canonical_content(text, 'text_input', {'response': {'accepted_answers': [{'text': '<main>'}, {'text': '<section>'}]}})
    text_root = etree.fromstring(question_to_openedx_olx(text).encode())
    assert text_root.find('.//stringresponse').get('answer') == '<main>'
    assert text_root.find('.//additional_answer').get('answer') == '<section>'


def test_real_uploaded_image_is_kept_as_an_image_not_escaped_text():
    media = QuestionMedia(id='image-1', alt_text='Ảnh <main> & ví dụ', sort_order=0)
    root = etree.fromstring(question_to_openedx_olx(make_question(), media=[media]).encode())
    image = root.find('.//img')
    assert image is not None
    assert image.get('alt') == 'Ảnh <main> & ví dụ'
    assert image.get('src') == '__ACMS_MEDIA_image-1__'


def test_hint_and_optional_source_content_keep_literal_code():
    question = make_question(
        source_ref='slide:<main>?a=1&b=2', source_excerpt='Ví dụ <details> & phần tử HTML.',
        pedagogy_json={'hint': 'So sánh <em> & <strong> với văn bản thường.'},
    )
    root = etree.fromstring(question_to_openedx_olx(question, include_source_in_solution=True).encode())
    assert _visible(root.find('.//demandhint/hint')).text_content() == (
        'Gợi ý nhỏ: So sánh <em> & <strong> với văn bản thường.')
    paragraphs = root.findall('.//solution/div/p')
    assert _visible(paragraphs[1]).text_content() == 'Nguồn: slide:<main>?a=1&b=2'
    assert _visible(paragraphs[2]).text_content() == 'Ví dụ <details> & phần tử HTML.'


def test_multiline_code_keeps_text_and_indentation():
    code = '<div>\n  <strong>Xin chào & chào mừng</strong>\n</div>'
    question = make_question(question_text=code)
    root = etree.fromstring(question_to_openedx_olx(question).encode())
    assert _visible(root.find('.//label')).text_content() == code
