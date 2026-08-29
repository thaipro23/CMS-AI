from pathlib import Path
from datetime import datetime
import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTerm,
    UdemySubjectPlan,
    UdemySubjectPlanMilestone,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.schemas.academic import AcademicSubjectDeliveryListOut


ROOT = Path(__file__).resolve().parents[3]


def _session():
    engine = create_engine('sqlite:///:memory:')
    for table in [
        AcademicTerm.__table__,
        AcademicBlock.__table__,
        AcademicSubject.__table__,
        AcademicSubjectDelivery.__table__,
        AcademicClass.__table__,
        UdemySubjectPlan.__table__,
        UdemySubjectPlanMilestone.__table__,
    ]:
        table.create(engine)
    return sessionmaker(bind=engine)()


def test_term_management_aggregates_blocks_and_detects_mixed_platform():
    db = _session()
    term = AcademicTerm(id='term-1', term_code='SU26', term_name='Summer 2026', branch='poly', active=True)
    block1 = AcademicBlock(id='block-1', term_id=term.id, block_code='B1', block_name='Block 1', sort_order=1, active=True)
    block2 = AcademicBlock(id='block-2', term_id=term.id, block_code='B2', block_name='Block 2', sort_order=2, active=True)
    subject = AcademicSubject(id='subject-1', subject_code='SOF3032', subject_name='Java nâng cao', branch='poly', active=True)
    d1 = AcademicSubjectDelivery(id='delivery-1', subject_id=subject.id, term_id=term.id, block_id=block1.id, branch='poly', learning_platform='cms', active=True)
    d2 = AcademicSubjectDelivery(id='delivery-2', subject_id=subject.id, term_id=term.id, block_id=block2.id, branch='poly', learning_platform='udemy', active=True)
    c1 = AcademicClass(id='class-1', term_id=term.id, block_id=block1.id, subject_id=subject.id, class_code='SOF3032.01', class_name='SOF3032.01', branch='poly', campus='ph', active=True)
    c2 = AcademicClass(id='class-2', term_id=term.id, block_id=block2.id, subject_id=subject.id, class_code='SOF3032.02', class_name='SOF3032.02', branch='poly', campus='ph', active=True)
    db.add_all([term, block1, block2, subject, d1, d2, c1, c2])
    db.commit()

    service = AcademicSubjectDeliveryService(db)
    result = service.list_deliveries(term_id=term.id, branch='poly', management_scope='term')

    validated = AcademicSubjectDeliveryListOut.model_validate(result)
    assert validated.total == 1
    assert validated.items[0].block_count == 2
    assert result['total'] == 1
    assert result['summary']['mixed_count'] == 1
    assert result['summary']['class_count'] == 2
    item = result['items'][0]
    assert item['subject_code'] == 'SOF3032'
    assert item['block_count'] == 2
    assert item['delivery_ids'] == ['delivery-1', 'delivery-2']
    assert item['platform_consistent'] is False
    assert set(item['platform_values']) == {'cms', 'udemy'}

    mixed = service.list_deliveries(term_id=term.id, branch='poly', learning_platform='mixed', management_scope='term')
    assert mixed['total'] == 1

    service.bulk_set_platform(item['delivery_ids'], 'udemy', actor='admin')
    unified = service.list_deliveries(term_id=term.id, branch='poly', management_scope='term')
    assert unified['summary']['udemy_count'] == 1
    assert unified['summary']['mixed_count'] == 0
    assert unified['items'][0]['learning_platform'] == 'udemy'
    assert unified['items'][0]['platform_consistent'] is True


def test_new_term_catalog_carries_forward_previous_term_platform(monkeypatch):
    db = _session()
    old_term = AcademicTerm(id='term-old', term_code='SP26', term_name='Spring 2026', branch='poly', start_date=datetime(2026, 1, 5), end_date=datetime(2026, 4, 30), active=True)
    new_term = AcademicTerm(id='term-new', term_code='SU26', term_name='Summer 2026', branch='poly', start_date=datetime(2026, 5, 5), end_date=datetime(2026, 8, 30), active=True)
    old_block = AcademicBlock(id='block-old', term_id=old_term.id, block_code='B1', block_name='Block 1', sort_order=1, active=True)
    new_block1 = AcademicBlock(id='block-new-1', term_id=new_term.id, block_code='B1', block_name='Block 1', sort_order=1, active=True)
    new_block2 = AcademicBlock(id='block-new-2', term_id=new_term.id, block_code='B2', block_name='Block 2', sort_order=2, active=True)
    subject = AcademicSubject(id='subject-1', subject_code='SOF3032', subject_name='Java nâng cao', branch='poly', active=True)
    previous = AcademicSubjectDelivery(id='delivery-old', subject_id=subject.id, term_id=old_term.id, block_id=old_block.id, branch='poly', learning_platform='udemy', active=True)
    db.add_all([old_term, new_term, old_block, new_block1, new_block2, subject, previous])
    db.commit()

    monkeypatch.setattr(
        'app.services.academic.subject_delivery.APAcademicClient.get_subjects',
        lambda _self, **_kwargs: [{'subject_code': 'SOF3032'}],
    )
    monkeypatch.setattr(
        'app.services.academic.subject_delivery.AcademicImportService.import_subject_catalog',
        lambda _self, _rows, **_kwargs: None,
    )

    result = AcademicSubjectDeliveryService(db).refresh_catalog(term_id=new_term.id, block_id=None, branch='poly', actor='admin')
    assert result['delivery_created'] == 2
    new_rows = db.query(AcademicSubjectDelivery).filter(AcademicSubjectDelivery.term_id == new_term.id).order_by(AcademicSubjectDelivery.block_id).all()
    assert len(new_rows) == 2
    assert all(row.learning_platform == 'udemy' for row in new_rows)
    assert all(row.configuration_source == 'previous_term_carry_forward' for row in new_rows)
    assert result['inherited_subject_count'] == 1


def test_mixed_previous_term_is_not_inherited(monkeypatch):
    db = _session()
    old_term = AcademicTerm(id='term-old-mixed', term_code='FA25', term_name='Fall 2025', branch='poly', start_date=datetime(2025, 9, 1), end_date=datetime(2025, 12, 31), active=True)
    new_term = AcademicTerm(id='term-new-mixed', term_code='SP26', term_name='Spring 2026', branch='poly', start_date=datetime(2026, 1, 5), end_date=datetime(2026, 4, 30), active=True)
    old_block1 = AcademicBlock(id='old-mixed-b1', term_id=old_term.id, block_code='B1', block_name='Block 1', sort_order=1, active=True)
    old_block2 = AcademicBlock(id='old-mixed-b2', term_id=old_term.id, block_code='B2', block_name='Block 2', sort_order=2, active=True)
    new_block = AcademicBlock(id='new-mixed-b1', term_id=new_term.id, block_code='B1', block_name='Block 1', sort_order=1, active=True)
    subject = AcademicSubject(id='subject-mixed', subject_code='WEB201', subject_name='Web nâng cao', branch='poly', active=True)
    db.add_all([
        old_term, new_term, old_block1, old_block2, new_block, subject,
        AcademicSubjectDelivery(id='old-mixed-d1', subject_id=subject.id, term_id=old_term.id, block_id=old_block1.id, branch='poly', learning_platform='cms', active=True),
        AcademicSubjectDelivery(id='old-mixed-d2', subject_id=subject.id, term_id=old_term.id, block_id=old_block2.id, branch='poly', learning_platform='udemy', active=True),
    ])
    db.commit()

    monkeypatch.setattr(
        'app.services.academic.subject_delivery.APAcademicClient.get_subjects',
        lambda _self, **_kwargs: [{'subject_code': 'WEB201'}],
    )
    monkeypatch.setattr(
        'app.services.academic.subject_delivery.AcademicImportService.import_subject_catalog',
        lambda _self, _rows, **_kwargs: None,
    )

    result = AcademicSubjectDeliveryService(db).refresh_catalog(term_id=new_term.id, block_id=None, branch='poly', actor='admin')
    row = db.query(AcademicSubjectDelivery).filter(AcademicSubjectDelivery.term_id == new_term.id).one()
    assert row.learning_platform is None
    assert row.configuration_source == 'ap_catalog'
    assert result['inherited_subject_count'] == 0


def test_batch35_2_cross_layer_contract():
    service = (ROOT / 'backend/app/services/academic/subject_delivery.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/app/subject-management/page.tsx').read_text(encoding='utf-8')
    api = (ROOT / 'frontend/lib/api.ts').read_text(encoding='utf-8')

    assert 'class_branch_key = func.lower(func.coalesce(AcademicClass.branch, literal_column("\'\'")))' in service
    assert '.group_by(AcademicClass.subject_id, AcademicClass.term_id, AcademicClass.block_id, class_branch_key)' in service
    assert "management_scope: str | None = Query(None)" in routes
    assert "managementScope: 'term'" in frontend
    assert 'Chọn học kỳ' in frontend
    assert '<label>Block<select' not in frontend
    assert 'Kỳ mới kế thừa lựa chọn CMS/Udemy nhất quán' in frontend
    assert 'Vận hành theo Block' in frontend
    assert "params.set('management_scope', filters.managementScope)" in api


def test_batch35_2_version_and_no_migration_contract():
    version = '25.9.16.7.2.64.16.5.7.2.18'
    markers = {
        '.env.example': f'APP_VERSION={version}',
        '.env.production.example': f'APP_VERSION={version}',
        'docker-compose.prod.yml': f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{version}}}',
        'frontend/Dockerfile': f'ARG NEXT_PUBLIC_APP_VERSION={version}',
        'backend/app/core/config.py': f"app_version: str = '{version}'",
        'frontend/package.json': f'"version": "{version}"',
        'e2e/package.json': f'"version": "{version}"',
    }
    for relative, marker in markers.items():
        assert marker in (ROOT / relative).read_text(encoding='utf-8')
    assert (ROOT / 'backend/alembic/versions/0059_v25_9_16_7_2_64_37_question_bank_legacy_hygiene.py').exists()
    assert (ROOT / 'backend/alembic/versions/0060_v25_9_16_7_2_64_38_question_authoring_types_media.py').exists()
    assert (ROOT / 'backend/alembic/versions/0061_v25_9_16_7_2_64_39_quiz_blueprint_type_quota.py').exists()
