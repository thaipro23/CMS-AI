"""The operator repair must reject another subject/version or a partial scope."""
from types import SimpleNamespace

import pytest

from republish_web3023_releases import OFFERING_ID, validate_scope
from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService


def scope():
    offering = SimpleNamespace(id=OFFERING_ID, subject_id='web')
    subject = SimpleNamespace(id='web', code='WEB3023')
    chapters = [SimpleNamespace(chapter_no=i, subject_offering_id=OFFERING_ID, subject_id='web')
                for i in range(1, 9)]
    return offering, subject, chapters


def test_accepts_exact_requested_eight_chapters():
    validate_scope(*scope())


def test_selects_eight_quiz_chapters_when_offering_also_has_final_test():
    offering, subject, chapters = scope()
    quizzes = list(chapters)
    final = SimpleNamespace(chapter_no=9, subject_offering_id=OFFERING_ID,
                            subject_id='web', title='Final test')
    chapters.append(final)
    selected = validate_scope(offering, subject, chapters)
    assert selected == quizzes
    assert final not in selected


def test_final_test_cannot_replace_a_missing_quiz_chapter():
    offering, subject, chapters = scope()
    chapters[-1] = SimpleNamespace(chapter_no=9, subject_offering_id=OFFERING_ID,
                                   subject_id='web', title='Final test')
    with pytest.raises(ValueError):
        validate_scope(offering, subject, chapters)


@pytest.mark.parametrize('change', ['subject', 'offering', 'missing', 'duplicate', 'foreign_chapter'])
def test_rejects_other_or_incomplete_scope(change):
    offering, subject, chapters = scope()
    if change == 'subject':
        subject.code = 'DOM1021'
    elif change == 'offering':
        offering.id = 'another-offering'
    elif change == 'missing':
        chapters.pop()
    elif change == 'duplicate':
        chapters[-1].chapter_no = 1
    else:
        chapters[-1].subject_offering_id = 'another-offering'
    with pytest.raises(ValueError):
        validate_scope(offering, subject, chapters)


@pytest.mark.parametrize('change', [None, 'library', 'canonical_key', 'membership', 'legacy_id'])
def test_repair_identity_accepts_only_unchanged_canonical_mapping(change):
    workflow = QuestionBankReleasePublishWorkflowService(SimpleNamespace())
    question_id = '12345678-1234-1234-1234-123456789abc'
    library = 'lib:FPT:web3023-su26-bai-1-v1'
    release = SimpleNamespace(openedx_library_key=library)
    item = SimpleNamespace(question_id=question_id, openedx_library_problem_id=(
        f'lb:FPT:web3023-su26-bai-1-v1:problem:ai-{question_id}'))
    expected = {'library_key': library, 'components': {question_id: item.openedx_library_problem_id}}
    canonical = library
    if change == 'library':
        release.openedx_library_key = 'lib:FPT:other'
    elif change == 'canonical_key':
        canonical = 'lib:FPT:new-title-or-term'
    elif change == 'membership':
        expected['components'] = {}
    elif change == 'legacy_id':
        item.openedx_library_problem_id = 'old-component'
        expected['components'][question_id] = 'old-component'
    if change is None:
        workflow._validate_repair_identity(release, [item], expected, canonical)
    else:
        with pytest.raises(ValueError, match='identity|identities'):
            workflow._validate_repair_identity(release, [item], expected, canonical)
