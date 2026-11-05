"""A failed republish must not delete questions that learners already use."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.question_bank import QuestionBankRelease, QuestionBankVersion, Subject, SubjectChapter
from app.services.question_bank import release_publish as module


@pytest.mark.parametrize('force,created,verify_raises,should_delete', [
    (True, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
    (False, False, False, False),
    (False, None, False, False),
    (False, 'true', False, False),
    (False, True, False, True),
    (False, True, True, True),
])
def test_failed_publish_preserves_existing_or_unproven_components(
    monkeypatch, force, created, verify_raises, should_delete,
):
    release = SimpleNamespace(id='release', bank_version_id='version', subject_id='subject',
        chapter_id='chapter', status='published' if force else 'draft', published_at=None,
        openedx_library_key='library', title='WEB3023', release_code='release-v1', metadata_json={})
    version = SimpleNamespace(id='version', version_code='v1', chapter_id='chapter')
    subject = SimpleNamespace(id='subject', code='WEB3023', name='Web')
    chapter = SimpleNamespace(id='chapter', chapter_no=1, title='Bài 1')
    question = SimpleNamespace(id='question', question_family_id=None, difficulty='easy',
                               question_text='<section id="sidebar">')
    item = SimpleNamespace(question_id='question', openedx_library_problem_id=None)
    objects = {QuestionBankRelease: release, QuestionBankVersion: version,
               Subject: subject, SubjectChapter: chapter}
    db = MagicMock()
    db.get.side_effect = lambda model, identity: objects[model]
    service = SimpleNamespace(db=db, _safe_refresh_chapter_stats=lambda chapter_id: None)
    workflow = module.QuestionBankReleasePublishWorkflowService(service)
    for name, value in {
        '_load_frozen_release_snapshot': lambda release: ([item], [question]),
        '_release_membership_hash': lambda ids: 'hash',
        '_release_publish_course_id': lambda *args: 'course',
        'release_library_key': lambda **kwargs: 'library',
        '_library_key_same': lambda a, b: a == b,
        '_release_library_key_needs_term_upgrade': lambda **kwargs: False,
        '_release_offering_term_slug': lambda **kwargs: 'SU26',
        '_canonical_library_org': lambda: 'FPL',
        '_chapter_display_name': lambda chapter: chapter.title,
    }.items():
        monkeypatch.setattr(workflow, name, value, raising=False)

    # Model external persistence: rollback deletion really removes the component.
    remote = {}

    class Connector:
        async def ensure_problem_library(self, **kwargs):
            return {'library_key': 'library'}

        async def import_problem_to_library(self, **kwargs):
            remote['component'] = kwargs['olx']
            result = {'problem_id': 'component'}
            if created is not None:
                result['created'] = created
            return result

        async def verify_library_problem(self, *args, **kwargs):
            if verify_raises:
                raise TimeoutError('verification timed out')
            return {'ok': False, 'status': 'verification_failed'}

        async def delete_library_problem(self, course_id, library_key, problem_id, **kwargs):
            remote.pop(problem_id)

    monkeypatch.setattr(module.settings, 'use_mock_openedx', False)
    monkeypatch.setattr(module, 'get_openedx_connector', lambda: Connector())
    monkeypatch.setattr(module, 'build_openedx_question_assets', lambda *args: ([], []))
    monkeypatch.setattr(module, 'question_to_openedx_olx', lambda *args, **kwargs: '<problem/>')
    with pytest.raises(RuntimeError, match='verify|verification'):
        asyncio.run(workflow.publish_release_to_openedx(release_id='release', force_reimport=force))
    assert ('component' not in remote) is should_delete
    assert release.status == 'publish_failed'
