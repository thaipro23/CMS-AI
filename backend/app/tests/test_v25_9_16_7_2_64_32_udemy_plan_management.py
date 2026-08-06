from io import BytesIO
from pathlib import Path
import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
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
from app.services.academic.udemy_plan import UdemyPlanService

ROOT = Path(__file__).resolve().parents[3]


def _session():
    engine = create_engine('sqlite:///:memory:')
    for table in [
        AcademicTerm.__table__, AcademicBlock.__table__, AcademicSubject.__table__,
        AcademicSubjectDelivery.__table__, AcademicClass.__table__, UdemySubjectPlan.__table__, UdemySubjectPlanMilestone.__table__,
    ]:
        table.create(engine)
    return sessionmaker(bind=engine)()


def _seed(db, *, platform='udemy'):
    term = AcademicTerm(id='term-fa23', term_code='FA2023', term_name='Fall 2023', branch='poly', active=True)
    block = AcademicBlock(id='block-1', term_id=term.id, block_code='Block 1', block_name='Block 1', sort_order=1, active=True)
    subject = AcademicSubject(id='subject-log301', subject_code='LOG301', subject_name='Quản trị chuỗi cung ứng', branch='poly', active=True)
    delivery = AcademicSubjectDelivery(id='delivery-log301', subject_id=subject.id, term_id=term.id, block_id=block.id, branch='poly', learning_platform=platform, active=True)
    db.add_all([term, block, subject, delivery])
    db.commit()
    return delivery


def _workbook_bytes(*, final_progress=100):
    wb = Workbook()
    ws = wb.active
    ws.append(['Import Setup Môn Học Udemy - ACMS'])
    ws.append(['STT', 'Học kỳ', 'Block', 'Mã môn học', 'Tên môn học', 'Số lượng Item', 'Week 1', 'Tiến độ week 1', 'Week 2', 'Tiến độ week 2', 'Week 3', 'Tiến độ week 3'])
    ws.append([1, 'Fall 2023', 'Block 1', 'LOG301', 'LOG301 - Quản trị chuỗi cung ứng', 6, 45207, 20, '14/10/2023', 60, '2023-10-21', final_progress])
    raw = BytesIO()
    wb.save(raw)
    return raw.getvalue()


def test_parse_real_acms_shape_and_commit_version_history():
    db = _session()
    delivery = _seed(db)
    service = UdemyPlanService(db)
    parsed = service.parse_workbook(_workbook_bytes(), filename='udemy_setup.xlsx', branch='poly', requested_by='admin-1')

    assert parsed['total_rows'] == 1
    assert parsed['valid_count'] == 1
    assert parsed['error_count'] == 0
    assert parsed['can_commit'] is True
    assert parsed['rows'][0]['delivery_id'] == delivery.id
    assert parsed['rows'][0]['milestones'][0]['deadline_date'] == '2023-10-08'
    assert parsed['rows'][0]['milestones'][-1]['required_progress_percent'] == 100

    parsed['preview_token'] = 'a' * 32
    first = service.commit_preview(parsed, actor='admin-1')
    assert len(first) == 1
    assert first[0].version == 1
    assert first[0].active is True
    assert db.query(UdemySubjectPlanMilestone).count() == 3

    # Retrying the same preview must be idempotent even if the HTTP response was lost.
    retry = service.commit_preview(parsed, actor='admin-1')
    assert retry[0].id == first[0].id
    assert db.query(UdemySubjectPlan).count() == 1
    assert db.query(UdemySubjectPlanMilestone).count() == 3

    parsed_again = service.parse_workbook(_workbook_bytes(), filename='udemy_setup-v2.xlsx', branch='poly', requested_by='admin-1')
    parsed_again['preview_token'] = 'b' * 32
    second = service.commit_preview(parsed_again, actor='admin-1')
    assert second[0].version == 2
    history = service.list_plan_history(delivery.id)
    assert [item['version'] for item in history] == [2, 1]
    assert history[0]['active'] is True
    assert history[1]['active'] is False


def test_parser_rejects_non_udemy_and_decreasing_progress():
    db = _session()
    _seed(db, platform='cms')
    service = UdemyPlanService(db)
    parsed = service.parse_workbook(_workbook_bytes(final_progress=30), filename='bad.xlsx', branch='poly', requested_by='admin-1')
    assert parsed['can_commit'] is False
    messages = ' '.join(item['message'] for item in parsed['errors'])
    assert 'nền tảng CMS' in messages
    assert 'không được giảm' in messages


def test_manual_plan_validation_and_delivery_summary():
    db = _session()
    delivery = _seed(db)
    service = UdemyPlanService(db)
    plan = service.create_version(
        delivery_id=delivery.id,
        item_count=8,
        milestones=[
            {'week_number': 1, 'deadline_date': '2026-08-10', 'required_progress_percent': 30},
            {'week_number': 2, 'deadline_date': '2026-08-17', 'required_progress_percent': 100},
        ],
        actor='admin-1',
        source='manual',
    )
    assert plan.version == 1
    listed = AcademicSubjectDeliveryService(db).list_deliveries(term_id='term-fa23', block_id='block-1', branch='poly')
    item = listed['items'][0]
    assert item['has_udemy_plan'] is True
    assert item['udemy_plan_version'] == 1
    assert item['udemy_item_count'] == 8
    assert item['udemy_milestone_count'] == 2

    with pytest.raises(HTTPException):
        service.create_version(
            delivery_id=delivery.id,
            item_count=8,
            milestones=[
                {'week_number': 1, 'deadline_date': '2026-08-17', 'required_progress_percent': 80},
                {'week_number': 2, 'deadline_date': '2026-08-10', 'required_progress_percent': 100},
            ],
            actor='admin-1',
            source='manual',
        )


def test_batch32_cross_layer_contracts():
    model = (ROOT / 'backend/app/models/academic.py').read_text(encoding='utf-8')
    migration = (ROOT / 'backend/alembic/versions/0055_v25_9_16_7_2_64_32_udemy_plans.py').read_text(encoding='utf-8')
    service = (ROOT / 'backend/app/services/academic/udemy_plan.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/app/subject-management/page.tsx').read_text(encoding='utf-8')
    editor = (ROOT / 'frontend/app/subject-management/[deliveryId]/udemy-plan/page.tsx').read_text(encoding='utf-8')

    assert 'class UdemySubjectPlan' in model
    assert 'class UdemySubjectPlanMilestone' in model
    assert "down_revision = '0054_v25_9_16_7_2_64_31'" in migration
    assert 'def parse_workbook' in service
    assert 'from_excel' in service
    assert "@router.post('/udemy/plans/import/preview'" in routes
    assert "@router.post('/udemy/plans/import/commit'" in routes
    assert "@router.post('/subject-deliveries/{delivery_id}/udemy-plan'" in routes
    assert 'Import kế hoạch Udemy' in frontend
    assert 'Lưu phiên bản' in editor
    assert 'edxkey.pem' not in '\n'.join(str(path) for path in ROOT.rglob('*'))
