"""Exercise connector helpers with an in-memory modulestore boundary.

Open edX/Django isn't installed in the AI Server image. Load the actual pure
helper definitions and substitute only the CMS store adapters.
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote
from xml.etree import ElementTree as ET


def connector_helpers():
    path = Path(__file__).resolve().parents[3] / 'openedx-connector-plugin/openedx_ai_connector/studio.py'
    tree = ast.parse(path.read_text())
    names = {'_safe_str', '_clean_usage_key', '_normalize_xblock_title', '_problem_bank_slot_display_name',
        '_field_value', '_block_field_snapshot', '_expected_library_component_refs', '_upstream_belongs_to_library',
        '_verify_native_itembank_block', '_apply_problem_display_name'}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *functions], type_ignores=[])
    def update(store, block, user, fields):
        for key, value in fields.items():
            setattr(block, key, value)
        store[block.location] = block
    namespace = {'json': json, 'unquote': unquote,
        '_block_type': lambda block: block.category,
        '_children_locations': lambda block: block.children,
        '_get_item_best_effort': lambda store, key: store.get(key),
        '_update_created_block_fields': update}
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace


def test_native_bank_verifies_ten_of_ten_but_rejects_eleven_of_ten():
    helpers = connector_helpers()
    bank = SimpleNamespace(location='bank', category='itembank', max_count=10, children=list(range(10)))
    store = {i: SimpleNamespace(location=f'problem{i}', category='problem', upstream=f'lb:FPT:test:problem:p{i}',
        parent='bank', upstream_version=1, data='<problem/>') for i in range(10)}
    slot = {'slot_no': 1, 'library_key': 'lib:FPT:test', 'pick_count': 10,
        'openedx_problem_ids': [child.upstream for child in store.values()]}
    assert helpers['_verify_native_itembank_block'](store, bank, slot)['selection_verified'] is True
    bank.max_count = 11
    assert helpers['_verify_native_itembank_block'](store, bank, {**slot, 'pick_count': 11})['selection_verified'] is False


def test_bank_titles_are_unique_even_when_concepts_are_equal_or_long():
    display_name = connector_helpers()['_problem_bank_slot_display_name']
    common = {'difficulty': 'EASY', 'family_names': ['Same concept ' * 80]}
    assert display_name({**common, 'slot_no': 1}) != display_name({**common, 'slot_no': 2})
    assert display_name({'slot_no': 1, 'difficulty': 'MEDIUM', 'sampling_strategy': 'difficulty_pool'}) == 'Nhóm 01 · Trung bình'


def test_course_copy_title_overrides_old_q1_without_altering_response_or_library():
    helper = connector_helpers()['_apply_problem_display_name']
    original = '<problem display_name="Q1"><choiceresponse><checkboxgroup><choice correct="true">A</choice><choice correct="true">B</choice><choice correct="false">C</choice></checkboxgroup></choiceresponse></problem>'
    library = SimpleNamespace(display_name='Q1', data=original)
    child = SimpleNamespace(location='course-copy', display_name=library.display_name, data=library.data, upstream='lb:FPT:test:problem:p1')
    store = {child.location: child}
    helper(store, 'staff', child, 'Câu hỏi: Chọn <hai> đáp án & giải thích')
    updated = ET.fromstring(child.data)
    assert updated.get('display_name') == child.display_name
    assert ET.tostring(updated.find('choiceresponse')) == ET.tostring(ET.fromstring(original).find('choiceresponse'))
    assert library.display_name == 'Q1' and library.data == original
    assert child.upstream == 'lb:FPT:test:problem:p1'
