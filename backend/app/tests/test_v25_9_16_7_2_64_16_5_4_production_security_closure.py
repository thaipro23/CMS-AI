from __future__ import annotations

import sys
import types

if 'openai' not in sys.modules:
    module = types.ModuleType('openai')
    module.AsyncOpenAI = object
    sys.modules['openai'] = module

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import course, job, question, question_bank  # noqa: F401
from app.models.question import Question
from app.models.question_bank import BankVersionDiff, LearningMaterialVersion, MaterialChunk
from app.schemas.question_bank import BankVersionDiffPreviewRequest
from app.services.question_bank_service import VersionedQuestionBankService


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_versions(db):
    svc = VersionedQuestionBankService(db)
    dept = svc.create_department(code='SEC', name='Security')
    subject = svc.create_subject(department_id=dept.id, code='SEC101', name='Security 101')
    chapter = svc.create_chapter(subject_id=subject.id, chapter_no=1, title='Bài 1')
    v1 = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v1.0', title='v1')
    v2 = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v2.0', title='v2', based_on_version_id=v1.id)
    for version, suffix in [(v1, '1'), (v2, '2')]:
        material = LearningMaterialVersion(id=f'mat-{suffix}', subject_id=subject.id, chapter_id=chapter.id, bank_version_id=version.id, title='slide', file_name='slide.txt', file_type='txt', storage_path='x', content_hash=f'hash-{suffix}', version_no=1, change_type='initial', status='indexed')
        db.add(material)
        db.add(MaterialChunk(id=f'chunk-{suffix}', material_version_id=material.id, bank_version_id=version.id, subject_id=subject.id, chapter_id=chapter.id, chunk_index=1, content='Nội dung bảo mật.', token_count=10, content_hash=f'chunk-hash-{suffix}'))
    db.add(Question(course_id=f'bank:{v1.id}', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=v1.id, difficulty='easy', question_text='Câu hỏi?', option_a='A', option_b='B', option_c='C', option_d='D', correct_answer='A', status='approved', question_family_id='fam', concept_key='sec', concept_title='Security', question_hash='qhash'))
    db.commit()
    return svc, v1, v2


def test_preview_is_read_only_and_create_is_idempotent():
    db = make_session()
    try:
        svc, v1, v2 = seed_versions(db)
        assert BankVersionDiffPreviewRequest().persist is False
        preview = svc.preview_bank_version_diff(from_bank_version_id=v1.id, to_bank_version_id=v2.id, actor='viewer')
        assert preview['diff_id'] is None
        assert db.query(BankVersionDiff).count() == 0
        created = svc.create_bank_version_diff(from_bank_version_id=v1.id, to_bank_version_id=v2.id, actor='admin')
        repeated = svc.create_bank_version_diff(from_bank_version_id=v1.id, to_bank_version_id=v2.id, actor='admin')
        assert created['diff_id'] == repeated['diff_id']
        assert repeated['idempotent_reuse'] is True
        assert db.query(BankVersionDiff).count() == 1
    finally:
        db.close()



def test_cookie_only_one_time_bridge_and_logout_contracts():
    from pathlib import Path

    app_root = Path(__file__).resolve().parents[1]
    auth_source = (app_root / 'api' / 'routes' / 'auth.py').read_text(encoding='utf-8')
    security_source = (app_root / 'core' / 'security.py').read_text(encoding='utf-8')
    connector_source = (app_root.parents[1] / 'openedx-connector-plugin' / 'openedx_ai_connector' / 'studio.py').read_text(encoding='utf-8')
    assert 'response_model_exclude_none=True' in auth_source
    assert 'access_token=None if is_production() else token' in auth_source
    assert 'claim_bridge_ticket_once' in auth_source
    assert "@router.post('/logout')" in auth_source
    assert "'jti': str(uuid.uuid4())" in auth_source
    assert 'is_session_revoked' in security_source
    assert "'jti': str(uuid.uuid4())" in connector_source
    assert 'max(30, min(' in connector_source


def test_no_route_returns_raw_exception_text():
    from pathlib import Path

    route_root = Path(__file__).resolve().parents[1] / 'api' / 'routes'
    matches = []
    for path in route_root.glob('*.py'):
        if 'detail=str(exc)' in path.read_text(encoding='utf-8'):
            matches.append(path.name)
    assert matches == []
