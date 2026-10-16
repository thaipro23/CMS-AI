import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.cost import get_course_policy
from app.core.rbac import UserContext
from app.db.session import Base
from app.models.cost import BudgetPolicy
from app.models import job  # noqa: F401 - register Question's generation FK.
from app.models.question import Question
from app.models.question_bank import LearningMaterialVersion, MaterialChunk, QuestionBankVersion, Subject, SubjectChapter
from app.schemas.question_bank import BankGeneratePreviewOut
from app.services.cost_control import CostControlService
from app.services.model_gateway import ModelGateway
from app.services.question_bank_service import VersionedQuestionBankService


@pytest.fixture
def bank(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    for table in Base.metadata.tables.values():
        table.create(engine)
    with Session(engine) as db:
        db.add_all([
            Subject(id='subject', department_id='department', code='SUB', name='Subject'),
            SubjectChapter(id='chapter', subject_id='subject', title='Bài 1'),
            QuestionBankVersion(id='bank', subject_id='subject', chapter_id='chapter', title='Bài 1'),
            LearningMaterialVersion(id='material', subject_id='subject', chapter_id='chapter', bank_version_id='bank'),
            MaterialChunk(id='chunk', subject_id='subject', chapter_id='chapter', bank_version_id='bank',
                          material_version_id='material', content='Tài liệu học tập về HTTP và REST API.', token_count=20),
            BudgetPolicy(scope='chapter', scope_id='default', max_questions_per_course=100, max_questions_per_job=100),
            BudgetPolicy(scope='course', scope_id='bank:bank', max_questions_per_course=100, max_questions_per_job=100),
        ])
        db.commit()
        async def local_pricing(self, **kwargs):
            return 0.001, None
        monkeypatch.setattr(CostControlService, 'calculate_cost_usd', local_pricing)
        yield db, VersionedQuestionBankService(db)
    engine.dispose()


def add_questions(db, count, *, source_type='bank_material', authoring_mode='ai', model_provider='openai', status='pending_review'):
    db.add_all([
        Question(course_id='bank:bank', bank_version_id='bank', subject_id='subject', subject_chapter_id='chapter',
                 question_text=f'{source_type} {status} {i}', option_a='A', option_b='B', option_c='C', option_d='D',
                 correct_answer='A', source_type=source_type, authoring_mode=authoring_mode,
                 model_provider=model_provider, status=status)
        for i in range(count)
    ])
    db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('imports', [30, 150])
async def test_imported_questions_do_not_reduce_ai_generation_capacity(bank, imports):
    db, service = bank
    add_questions(db, imports, source_type='manual_import', authoring_mode='import', model_provider='manual')
    preview = await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=100)
    assert preview['remaining_quota'] == 100
    assert preview['generated_question_count'] == 0
    assert preview['current_question_count'] == imports
    assert BankGeneratePreviewOut.model_validate(preview).model_dump()['generated_question_count'] == 0
    readiness = service.release_readiness(bank_version_id='bank')
    assert readiness['stats']['chapter_total_count'] == imports
    assert readiness['stats']['chapter_generated_count'] == 0
    assert readiness['stats']['chapter_remaining_quota'] == 100


@pytest.mark.asyncio
async def test_only_ai_questions_spend_chapter_quota_across_review_states(bank):
    db, service = bank
    add_questions(db, 30, authoring_mode='import', model_provider='manual', source_type='manual_import')
    for status in ('approved', 'pending_review', 'rejected', 'draft_error'):
        add_questions(db, 5, status=status)
    preview = await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=80)
    assert preview['remaining_quota'] == 80
    assert preview['generated_question_count'] == 20
    with pytest.raises(ValueError, match='chỉ còn'):
        await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=81)
    with pytest.raises(ValueError, match='chỉ còn'):
        await service.generate_from_bank_version(bank_version_id='bank', question_count=81)


@pytest.mark.asyncio
@pytest.mark.parametrize(('source', 'mode', 'provider'), [
    ('legacy_quiz_excel', 'ai', 'openai'),  # Historical defaulted provenance.
    ('openedx_import', 'import', 'manual'),
    ('manual_import', 'ai', 'manual'),
    ('manual', 'manual', 'manual'),
])
async def test_legacy_import_and_manual_origins_do_not_spend_quota(bank, source, mode, provider):
    db, service = bank
    add_questions(db, 30, source_type=source, authoring_mode=mode, model_provider=provider)
    preview = await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=100)
    assert preview['remaining_quota'] == 100
    assert CostControlService(db).check_quota('bank:bank', 100)[0] is True
    policy = await get_course_policy('bank:bank', db, UserContext(user_id='admin', role='admin', permissions=set()))
    assert policy.generated_questions == 0
    assert policy.remaining_questions == 100


@pytest.mark.asyncio
@pytest.mark.parametrize('material_source', ['file', 'legacy_quiz_excel'])
async def test_generation_worker_can_create_full_ai_quota_after_import(bank, monkeypatch, material_source):
    db, service = bank
    db.get(MaterialChunk, 'chunk').source_type = material_source
    add_questions(db, 30, source_type='manual_import', authoring_mode='import', model_provider='manual')
    async def generate(self, *, question_count, **kwargs):
        return [
            {'question': f'Câu hỏi HTTP mới số {i}?', 'difficulty': 'easy',
             'options': {'A': 'Đúng', 'B': 'Sai', 'C': 'Khác', 'D': 'Không rõ'},
             'correct_answer': 'A', 'source_chunk_id': 'chunk', 'source_evidence': 'HTTP và REST API.'}
            for i in range(question_count)
        ], {}
    monkeypatch.setattr(ModelGateway, 'generate_questions', generate)
    result = await service.generate_from_bank_version(
        bank_version_id='bank', question_count=100, difficulty_easy=100, difficulty_medium=0, difficulty_hard=0,
    )
    assert result['created_questions'] == 100
    assert db.query(Question).count() == 130
    with pytest.raises(ValueError, match='chỉ còn'):
        await service.generate_from_bank_version(bank_version_id='bank', question_count=1)


@pytest.mark.asyncio
async def test_copying_legacy_imports_preserves_their_free_generation_capacity(bank):
    db, service = bank
    add_questions(db, 30, source_type='legacy_quiz_excel', status='approved')
    db.add(QuestionBankVersion(id='bank2', subject_id='subject', chapter_id='chapter', version_code='v2'))
    db.commit()
    result = service.carry_over_questions(from_bank_version_id='bank', to_bank_version_id='bank2')
    assert result['created_count'] == 30
    preview = await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=100)
    assert preview['generated_question_count'] == 0
    assert preview['remaining_quota'] == 100


def test_cloning_subject_offering_preserves_legacy_import_origin(bank):
    db, service = bank
    source = service.create_subject_offering(subject_id='subject', term='SU26')
    db.get(SubjectChapter, 'chapter').subject_offering_id = source.id
    db.get(QuestionBankVersion, 'bank').subject_offering_id = source.id
    db.commit()
    add_questions(db, 30, source_type='legacy_quiz_excel', status='approved')
    target = service.create_subject_offering(subject_id='subject', term='FA26', clone_from_offering_id=source.id)
    chapter = db.query(SubjectChapter).filter_by(subject_offering_id=target.id).one()
    questions = db.query(Question).filter_by(subject_chapter_id=chapter.id).all()
    assert len(questions) == 30
    assert {q.authoring_mode for q in questions} == {'import'}
    assert service._chapter_generated_question_count(chapter_id=chapter.id) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('copy_source', ['bank_carry_over', 'subject_offering_clone'])
@pytest.mark.parametrize('ai_origin', [False, True])
async def test_existing_copies_use_persisted_origin_for_ai_quota(bank, copy_source, ai_origin):
    db, service = bank
    add_questions(db, 30, source_type='legacy_quiz_excel', status='approved')
    originals = db.query(Question).all()
    if ai_origin:
        for question in originals:
            question.source_node_id = 'bank-version:bank:material:material'
    db.add_all([
        Question(course_id='bank:bank', bank_version_id='bank', subject_id='subject', subject_chapter_id='chapter',
                 question_text=f'Historical clone {q.id}', option_a='A', option_b='B', option_c='C', option_d='D',
                 correct_answer='A', source_type=copy_source, authoring_mode='ai', model_provider='openai',
                 previous_question_id=q.id, lineage_root_question_id=q.id, is_carry_over=True)
        for q in originals
    ])
    db.commit()
    remaining = 40 if ai_origin else 100
    preview = await service.preview_generate_from_bank_version(bank_version_id='bank', question_count=remaining)
    assert preview['generated_question_count'] == (60 if ai_origin else 0)
    assert preview['current_question_count'] == 60
    assert preview['remaining_quota'] == remaining
    assert CostControlService(db).check_quota('bank:bank', remaining)[0] is True
    assert CostControlService(db).check_quota('bank:bank', remaining + 1)[0] is False
