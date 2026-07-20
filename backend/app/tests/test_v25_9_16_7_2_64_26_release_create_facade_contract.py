from __future__ import annotations

import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_create_facade_accepts_complete_api_payload_contract():
    source = (ROOT / 'app/services/question_bank_service.py').read_text()
    body = source.split('    def create_release(', 1)[1].split('    def cancel_failed_release', 1)[0]

    for field in (
        'bank_version_id: str',
        'release_code: str | None = None',
        "title: str = ''",
        'include_approved_questions: bool = True',
        'actor: str | None = None',
        'force: bool = False',
    ):
        assert field in body

    assert 'release_code=release_code' in body
    assert 'include_approved_questions=include_approved_questions' in body
    assert 'force=force' in body


def test_release_route_forwards_bank_release_create_model_dump():
    route = (ROOT / 'app/api/routes/question_bank_v2.py').read_text()
    assert 'VersionedQuestionBankService(db).create_release(**payload.model_dump(), actor=user.user_id)' in route
