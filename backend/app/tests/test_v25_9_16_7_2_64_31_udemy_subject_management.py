from pathlib import Path
import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

import pytest
from fastapi import HTTPException
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


def _seed(db):
    term = AcademicTerm(id='term-1', term_code='Summer 2026', term_name='Summer 2026', branch='poly', active=True)
    block = AcademicBlock(id='block-1', term_id=term.id, block_code='Block 1', block_name='Block 1', sort_order=1, active=True)
    subject = AcademicSubject(id='subject-1', subject_code='SOF3032', subject_name='Lập trình Java nâng cao', branch='poly', active=True)
    delivery = AcademicSubjectDelivery(id='delivery-1', subject_id=subject.id, term_id=term.id, block_id=block.id, branch='poly', active=True)
    cls = AcademicClass(id='class-1', term_id=term.id, block_id=block.id, subject_id=subject.id, class_code='SOF3032.01', class_name='SOF3032.01', branch='poly', campus='ph', active=True)
    db.add_all([term, block, subject, delivery, cls])
    db.commit()
    return term, block, subject, delivery, cls


def test_subject_delivery_platform_scope_and_history():
    db = _session()
    _term, block, _subject, delivery, _cls = _seed(db)
    service = AcademicSubjectDeliveryService(db)

    listed = service.list_deliveries(term_id='term-1', block_id=block.id, branch='poly')
    assert listed['total'] == 1
    assert listed['items'][0]['subject_code'] == 'SOF3032'
    assert listed['items'][0]['class_count'] == 1
    assert listed['summary']['unassigned_count'] == 1

    updated = service.set_platform(delivery.id, 'udemy', actor='admin-1')
    assert updated.learning_platform == 'udemy'
    assert updated.metadata_json['platform_history'][-1]['from'] is None
    assert updated.metadata_json['platform_history'][-1]['to'] == 'udemy'

    service.set_platform(delivery.id, 'cms', actor='admin-1')
    db.refresh(delivery)
    assert delivery.learning_platform == 'cms'
    assert len(delivery.metadata_json['platform_history']) == 2


def test_catalog_refresh_is_idempotent_and_preserves_platform(monkeypatch):
    db = _session()
    term, block, _subject, delivery, _cls = _seed(db)
    db.delete(delivery)
    db.commit()

    monkeypatch.setattr(
        'app.services.academic.subject_delivery.APAcademicClient.get_subjects',
        lambda _self, **_kwargs: [{'subject_code': 'SOF3032'}],
    )
    monkeypatch.setattr(
        'app.services.academic.subject_delivery.AcademicImportService.import_subject_catalog',
        lambda _self, _rows, **_kwargs: None,
    )

    service = AcademicSubjectDeliveryService(db)
    first = service.refresh_catalog(term_id=term.id, block_id=block.id, branch='poly', actor='admin-1')
    assert first['delivery_created'] == 1
    row = db.query(AcademicSubjectDelivery).one()
    row.learning_platform = 'udemy'
    db.commit()

    second = service.refresh_catalog(term_id=term.id, block_id=block.id, branch='poly', actor='admin-2')
    assert second['delivery_created'] == 0
    assert second['delivery_updated'] == 1
    db.refresh(row)
    assert row.learning_platform == 'udemy'
    assert row.catalog_refreshed_at is not None


def test_udemy_delivery_blocks_cms_but_not_ap_roster_scope():
    db = _session()
    _term, _block, _subject, delivery, cls = _seed(db)
    delivery.learning_platform = 'udemy'
    db.commit()
    service = AcademicSubjectDeliveryService(db)

    with pytest.raises(HTTPException) as exc:
        service.assert_cms_workflow_allowed_for_class(cls.id, job_type='full_cms_sync')
    assert exc.value.status_code == 409
    assert 'Udemy' in str(exc.value.detail)

    assert service.is_subject_udemy_only(term_id='term-1', subject_id='subject-1', branch='poly') is True
    with pytest.raises(HTTPException) as mapping_exc:
        service.assert_subject_course_mapping_allowed(term_id='term-1', subject_id='subject-1', branch='poly')
    assert mapping_exc.value.status_code == 409


def test_batch31_cross_layer_contracts():
    model = (ROOT / 'backend/app/models/academic.py').read_text(encoding='utf-8')
    migration = (ROOT / 'backend/alembic/versions/0054_v25_9_16_7_2_64_31_subject_delivery.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    worker = (ROOT / 'backend/app/worker.py').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/app/subject-management/page.tsx').read_text(encoding='utf-8')
    shell = (ROOT / 'frontend/components/layout/AppShell.tsx').read_text(encoding='utf-8')

    assert 'class AcademicSubjectDelivery' in model
    assert "down_revision = '0053_v25_9_16_7_2_64_16_5_4'" in migration
    assert "@router.get('/subject-deliveries'" in routes
    assert "@router.post('/subject-deliveries/catalog-refresh/jobs'" in routes
    assert "@router.patch('/subject-deliveries/{delivery_id}/platform'" in routes
    assert "academic_subject_catalog_refresh_task" in worker
    assert "academic.class_sync.async.skipped_udemy" in worker
    assert "analytics.learning_behavior.recalculate.async.skipped_udemy" in worker
    assert "skip_reason': 'udemy_platform'" in worker
    assert 'Lấy danh sách tất cả môn' in frontend
    assert "value: 'cms'" in frontend and "value: 'udemy'" in frontend
    assert "href: '/subject-management'" in shell
    assert 'edxkey.pem' not in '\n'.join(str(path) for path in ROOT.rglob('*'))
