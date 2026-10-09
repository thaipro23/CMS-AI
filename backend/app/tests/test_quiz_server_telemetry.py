import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from lxml import etree

from app.services.learning_analytics.tracking_event_parser import parse_tracking_log_line
from app.services.learning_analytics.quiz_attempt_analyzer import EventLike, build_quiz_attempt_features

MODULE = Path(__file__).resolve().parents[3] / 'openedx-unit-reset-plugin/openedx_unit_reset/analytics.py'


def load_module():
    spec = importlib.util.spec_from_file_location('quiz_server_analytics', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def block(name='clone-a', data='<problem><p>Question</p></problem>', variant=''):
    key = f'block-v1:FPL+SUB+FA26+type@problem+block@{name}'
    unit = SimpleNamespace(location='block-v1:FPL+SUB+FA26+type@vertical+block@unit', category='vertical')
    input_id = name + '_2_1'
    root = etree.fromstring(f'<problem><p>Question</p><multiplechoiceresponse id="{name}_2"><choicegroup id="{input_id}"><choice>A</choice><choice>B</choice></choicegroup></multiplechoiceresponse></problem>')
    responder = SimpleNamespace(xml=root[1], answer_ids=[input_id])
    return SimpleNamespace(location=key, data=data, get_parent=lambda: unit,
        lcp=SimpleNamespace(responders={'response': responder})), {
        'problem_id': key, 'submission': {input_id: {
            'question': '', 'variant': variant, 'answer': 'A', 'correct': True,
            'response_type': 'multiplechoiceresponse'}}}


def test_metadata_comes_from_server_definition_and_is_stable_across_clones():
    module = load_module()
    a, payload_a = block('clone-a')
    b, payload_b = block('clone-b')
    before = json.dumps(payload_a, sort_keys=True)
    out_a = module.enrich_problem_check(a, payload_a)
    out_b = module.enrich_problem_check(b, payload_b)
    assert out_a['content_version'] == out_b['content_version']
    assert out_a['content_version'].startswith('sha256:')
    assert out_a['unit_usage_key'].endswith('type@vertical+block@unit')
    assert out_a['submission']['clone-a_2_1']['question_hash'] == out_b['submission']['clone-b_2_1']['question_hash']
    assert out_a['submission']['clone-a_2_1']['answer'] == 'A'
    assert json.dumps(payload_a, sort_keys=True) == before


def test_changed_definition_or_variant_is_not_the_same_question():
    module = load_module()
    a, p_a = block()
    b, p_b = block(data='<problem><p>Another question</p></problem>')
    c, p_c = block(variant='different')
    hashes = [module.enrich_problem_check(obj, payload)['submission']['clone-a_2_1']['question_hash']
              for obj, payload in [(a, p_a), (b, p_b), (c, p_c)]]
    assert len(set(hashes)) == 3


def test_no_definition_does_not_fabricate_a_version():
    module = load_module()
    obj, payload = block(data='')
    assert 'content_version' not in module.enrich_problem_check(obj, payload)


def test_publish_hook_is_idempotent_and_metadata_failure_does_not_break_submit():
    module = load_module()
    emitted = []
    class Capa:
        def publish_unmasked(self, title, payload):
            emitted.append((title, payload))
            return 'native-result'
    assert module.install_capa_tracking(Capa)
    assert not module.install_capa_tracking(Capa)
    obj = Capa()
    obj.data = 'definition'
    obj.location = 'problem'
    obj.get_parent = lambda: (_ for _ in ()).throw(RuntimeError('not loaded'))
    assert obj.publish_unmasked('problem_check', {'submission': {}}) == 'native-result'
    assert len(emitted) == 1


def test_successful_start_event_contains_actual_session_scope_and_survives_parser():
    module = load_module()
    emitted = []
    result = {'session': {'id': 42, 'course_id': 'course-v1:FPL+SUB+FA26',
        'unit_usage_key': 'block-v1:FPL+SUB+FA26+type@vertical+block@unit',
        'sequence_usage_key': 'sequence', 'started_at': '2026-10-07T09:00:00Z'}}
    assert module.emit_quiz_session_start(result, emit=lambda kind, payload: emitted.append((kind, payload)))
    kind, payload = emitted[0]
    parsed = parse_tracking_log_line(json.dumps({'event_type': kind, 'event': payload,
        'event_source': 'server', 'context': {'user_id': 1}, 'username': 'sv',
        'time': '2026-10-07T09:00:02Z'}))
    assert parsed.course_id == result['session']['course_id']
    attempt = build_quiz_attempt_features([EventLike(parsed.event_type, parsed.event_source,
        parsed.event_time, parsed.user_id, parsed.username, parsed.course_id,
        parsed.page_url, parsed.raw_event, parsed.raw_context, parsed.raw_json)])[0]
    assert attempt.start_observed
    assert attempt.started_at.isoformat() == '2026-10-07T09:00:00'


def test_installer_uses_actual_openedx_problem_block_export(monkeypatch):
    import sys
    from types import ModuleType
    module = load_module()
    native = ModuleType('xmodule.capa_block')
    class ProblemBlock:
        def publish_unmasked(self, title, payload):
            return payload
    native.ProblemBlock = ProblemBlock
    monkeypatch.setitem(sys.modules, 'xmodule', ModuleType('xmodule'))
    monkeypatch.setitem(sys.modules, 'xmodule.capa_block', native)
    assert module.install_capa_tracking()
    assert ProblemBlock.publish_unmasked._acms_quiz_analytics


def test_failed_or_unscoped_start_does_not_emit_a_personal_event():
    module = load_module()
    emitted = []
    assert not module.emit_quiz_session_start({'success': False}, emit=lambda *args: emitted.append(args))
    assert not emitted


def test_reset_records_the_actual_new_session_start_without_a_second_synthetic_start():
    module = load_module()
    emitted = []
    result = {'success': True, 'id': 43, 'course_id': 'course',
              'unit_usage_key': 'unit', 'started_at': '2026-10-07T09:05:00Z'}
    assert module.emit_quiz_session_start(result, reset=True,
        emit=lambda kind, payload: emitted.append((kind, payload)))
    assert len(emitted) == 1
    assert emitted[0][1]['reset_request'] is True
