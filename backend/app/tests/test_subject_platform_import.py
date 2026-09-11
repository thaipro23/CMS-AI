"""Excel platform plans must match the complete selected term, then apply atomically."""
import os
from io import BytesIO

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.academic import AcademicBlock, AcademicSubject, AcademicSubjectDelivery, AcademicTerm
from app.services.academic import subject_delivery


def _service():
    from app.services.academic.subject_platform_import import SubjectPlatformImportService
    engine = create_engine('sqlite:///:memory:')
    for model in [AcademicTerm, AcademicBlock, AcademicSubject, AcademicSubjectDelivery]:
        model.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    db.add(AcademicTerm(id='term', term_code='SU26', term_name='Summer', branch='poly', active=True))
    db.add(AcademicTerm(id='other-term', term_code='FA26', term_name='Fall', branch='poly', active=True))
    db.add_all([AcademicBlock(id=f'block-{i}', term_id='term', block_code=f'B{i}', block_name=f'Block {i}', active=True) for i in [1, 2]])
    for i in range(205):
        db.add(AcademicSubject(id=f's{i}', subject_code=f'SOF{i:03}', subject_name=f'Subject {i}', branch='poly', active=True))
        for block in [1, 2]:
            db.add(AcademicSubjectDelivery(id=f'd{i}-{block}', subject_id=f's{i}', term_id='term', block_id=f'block-{block}', branch='poly', active=True, learning_platform='cms'))
    db.add(AcademicSubjectDelivery(id='outside', subject_id='s204', term_id='other-term', block_id='block-1', branch='poly', active=True, learning_platform='cms'))
    db.commit()
    return db, SubjectPlatformImportService(db)


def _xlsx(rows, headers=('Mã môn', 'Nền tảng')):
    book = Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    raw = BytesIO()
    book.save(raw)
    return raw.getvalue()


def test_other_platform_is_a_distinct_explicit_choice():
    assert subject_delivery.AcademicSubjectDeliveryService.normalize_platform('Khác') == 'other'
    assert subject_delivery.AcademicSubjectDeliveryService.normalize_platform('OTHER') == 'other'
    assert subject_delivery.AcademicSubjectDeliveryService.normalize_platform(None) is None


def test_preview_and_apply_match_all_rows_case_insensitively_across_all_blocks():
    db, service = _service()
    preview = service.preview(_xlsx([(f' sof{i:03} ', ['cms', 'Udemy', 'Khác'][i % 3]) for i in range(205)]), term_id='term', branch='poly', requested_by='owner')
    assert preview['total_rows'] == 205
    assert preview['matched_count'] == 205
    assert preview['can_apply'] is True
    assert preview['rows'][-1]['delivery_ids'] == ['d204-1', 'd204-2']
    assert db.get(AcademicSubjectDelivery, 'd1-1').learning_platform == 'cms'
    result = service.apply_preview(preview, actor='owner')
    assert result['subjects'] == 205
    assert result['updated'] == 272
    assert db.get(AcademicSubjectDelivery, 'd2-1').learning_platform == 'other'
    assert db.get(AcademicSubjectDelivery, 'd1-2').learning_platform == 'udemy'
    assert db.get(AcademicSubjectDelivery, 'outside').learning_platform == 'cms'
    assert db.get(AcademicSubjectDelivery, 'd2-1').metadata_json['platform_history'][-1]['source'] == 'excel_plan_import'
    assert service.apply_preview(preview, actor='owner')['updated'] == 0


def test_invalid_missing_and_duplicate_rows_block_apply_without_partial_writes():
    db, service = _service()
    preview = service.preview(_xlsx([('sof001', 'udemy'), ('SOF002', 'cms'), ('sof002', 'Other'), ('missing', 'cms'), ('sof003', 'bad'), ('', 'cms')]), term_id='term', branch='poly', requested_by='owner')
    assert preview['matched_count'] == 1
    assert preview['duplicate_count'] == 2
    assert preview['missing_count'] == 1
    assert preview['invalid_count'] == 2
    assert preview['can_apply'] is False
    with pytest.raises(HTTPException) as error:
        service.apply_preview(preview, actor='owner')
    assert error.value.status_code == 422
    assert db.get(AcademicSubjectDelivery, 'd1-1').learning_platform == 'cms'


def test_apply_revalidates_active_targets_and_rejects_changed_scope():
    db, service = _service()
    preview = service.preview(_xlsx([('SOF001', 'udemy'), ('SOF002', 'udemy')]), term_id='term', branch='poly', requested_by='owner')
    db.get(AcademicSubjectDelivery, 'd2-2').active = False
    db.commit()
    with pytest.raises(HTTPException) as error:
        service.apply_preview(preview, actor='owner')
    assert error.value.status_code == 409
    assert db.get(AcademicSubjectDelivery, 'd1-1').learning_platform == 'cms'


@pytest.mark.parametrize('headers', [('Mã môn', 'Nền tảng', 'Hệ'), ('subject_code', 'platform'), ('Nền tảng', 'Mã môn')])
def test_exact_two_column_contract(headers):
    _, service = _service()
    with pytest.raises(HTTPException) as error:
        service.preview(_xlsx([('SOF001', 'cms')], headers=headers), term_id='term', branch='poly', requested_by='owner')
    assert error.value.status_code == 422


def test_term_branch_mismatch_is_rejected():
    _, service = _service()
    with pytest.raises(HTTPException) as error:
        service.preview(_xlsx([('SOF001', 'cms')]), term_id='term', branch='ptcd', requested_by='owner')
    assert error.value.status_code == 422
