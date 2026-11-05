import asyncio
from lxml import etree, html
import pytest

from republish_web3023_no_build import literal_olx, ExistingLibraryRepairConnector, protect_library_identity


def test_old_exporter_choices_become_literal_without_changing_grading():
    original = ('<problem><multiplechoiceresponse><label>Thẻ &lt;main&gt;?</label>'
        '<choicegroup><choice correct="true">&lt;section id="sidebar"&gt;</choice>'
        '<choice correct="false"><div>&lt;details&gt;</div></choice></choicegroup>'
        '</multiplechoiceresponse><stringresponse answer="&lt;main&gt;"/></problem>')
    root = etree.fromstring(literal_olx(original).encode())
    for choice, text in zip(root.findall('.//choice'), ['<section id="sidebar">', '<details>']):
        markup = (choice.text or '') + ''.join(etree.tostring(c, encoding='unicode') for c in choice)
        rendered = html.fragment_fromstring(markup, create_parent='div')
        assert rendered.text_content() == text
        assert not rendered.xpath('.//section | .//details')
    assert root.find('.//stringresponse').get('answer') == '<main>'
    assert [c.get('correct') for c in root.findall('.//choice')] == ['true', 'false']
    assert literal_olx(literal_olx(original)) == literal_olx(original)


@pytest.mark.parametrize('scenario', ['ok', 'missing', 'other_library', 'other_result_id', 'delete'])
def test_connector_refuses_create_switch_and_delete(scenario):
    state = {'imports': 0, 'deletes': 0}

    class Native:
        async def verify_library_problem(self, *args, **kwargs):
            return {'ok': True, 'library_exists': True, 'problem_exists': scenario != 'missing'}

        async def import_problem_to_library(self, **kwargs):
            state['imports'] += 1
            return {'problem_id': 'wrong' if scenario == 'other_result_id' else 'component'}

        async def delete_library_problem(self, *args, **kwargs):
            state['deletes'] += 1

    repair = ExistingLibraryRepairConnector(Native(), 'lib:FPT:existing', {'q': 'component'})
    async def operation():
        if scenario == 'delete':
            return await repair.delete_library_problem('course', 'lib:FPT:existing', 'component')
        return await repair.import_problem_to_library(
            course_id='course', library_key='other' if scenario == 'other_library' else 'lib:FPT:existing',
            olx='<problem/>', display_name='question', metadata={'question_id': 'q'})
    if scenario == 'ok':
        assert asyncio.run(operation())['problem_id'] == 'component'
    else:
        with pytest.raises(RuntimeError):
            asyncio.run(operation())
    assert state['deletes'] == 0
    assert state['imports'] == (1 if scenario in {'ok', 'other_result_id'} else 0)


def test_ensure_reuses_verified_library_without_calling_creation_api():
    repair = ExistingLibraryRepairConnector(object(), 'lib:FPT:existing', {'q': 'component'})
    result = asyncio.run(repair.ensure_problem_library('course', 'chapter', 'title',
                                                      {'library_key': 'lib:FPT:existing'}))
    assert result['library_key'] == 'lib:FPT:existing'
    assert result['status'] == 'repair_existing_library_only'
    with pytest.raises(RuntimeError):
        asyncio.run(repair.ensure_problem_library('course', 'chapter', 'title', {'library_key': 'other'}))


def test_identity_guard_blocks_actual_workflow_and_wrapper_and_restores_after_error():
    from app.services.question_bank_service import VersionedQuestionBankService as Parent
    from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService as Workflow
    originals = [owner._reset_release_openedx_state_for_key_change for owner in (Parent, Workflow)]
    with pytest.raises(ValueError, match='interrupted'):
        with protect_library_identity(Parent, Workflow):
            for owner in (Parent, Workflow):
                with pytest.raises(RuntimeError, match='identity reset'):
                    owner._reset_release_openedx_state_for_key_change(None)
            raise ValueError('interrupted')
    assert [owner._reset_release_openedx_state_for_key_change for owner in (Parent, Workflow)] == originals
