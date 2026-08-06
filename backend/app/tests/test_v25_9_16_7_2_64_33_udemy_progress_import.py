from datetime import date
from io import BytesIO
from pathlib import Path
import hashlib
import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.academic import (
    AcademicBlock,
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTerm,
    UdemyProgressImportBatch,
    UdemyProgressUnmatchedRow,
    UdemyStudentProgress,
    UdemySubjectPlan,
    UdemySubjectPlanMilestone,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.academic.udemy_progress import UdemyProgressService

ROOT = Path(__file__).resolve().parents[3]


def _session():
    engine = create_engine('sqlite:///:memory:')
    for table in [
        AcademicTerm.__table__, AcademicBlock.__table__, AcademicSubject.__table__,
        AcademicSubjectDelivery.__table__, AcademicStudent.__table__, AcademicClass.__table__,
        AcademicClassStudent.__table__, AcademicBulkOperationJob.__table__, UdemySubjectPlan.__table__,
        UdemySubjectPlanMilestone.__table__, UdemyProgressImportBatch.__table__,
        UdemyStudentProgress.__table__, UdemyProgressUnmatchedRow.__table__,
    ]:
        table.create(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    term = AcademicTerm(id='term-su26', term_code='SU26', term_name='Summer 2026', branch='poly', active=True)
    block = AcademicBlock(id='block-1', term_id=term.id, block_code='Block 1', block_name='Block 1', sort_order=1, active=True)
    subject = AcademicSubject(id='subject-sof3032', subject_code='SOF3032', subject_name='Java nâng cao', branch='poly', active=True)
    delivery = AcademicSubjectDelivery(id='delivery-sof3032', subject_id=subject.id, term_id=term.id, block_id=block.id, branch='poly', learning_platform='udemy', active=True)
    cls = AcademicClass(id='class-sof3032-1', term_id=term.id, block_id=block.id, subject_id=subject.id, class_code='SOF3032.01', class_name='SOF3032.01', campus='ph', branch='poly', active=True)
    student = AcademicStudent(id='student-1', student_code='PH00001', username='PH00001', email='student1@fpt.edu.vn', full_name='Sinh viên Một', campus='ph', branch='poly', active=True)
    link = AcademicClassStudent(id='link-1', class_id=cls.id, student_id=student.id, source='ap')
    plan = UdemySubjectPlan(id='plan-1', subject_delivery_id=delivery.id, version=1, item_count=2, active=True, source='manual')
    milestone = UdemySubjectPlanMilestone(id='milestone-1', plan_id=plan.id, week_number=1, deadline_date=date(2026, 1, 1), required_progress_percent=80, sort_order=1)
    db.add_all([term, block, subject, delivery, cls, student, link, plan, milestone])
    db.commit()
    return delivery, subject


def _save_workbook(path: Path, rows: list[list], *, title=True):
    wb = Workbook()
    ws = wb.active
    if title:
        ws.append(['Báo cáo tiến độ Udemy'])
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


def test_parse_aggregate_and_legacy_25_column_formats(tmp_path):
    db = _session()
    delivery, _subject = _seed(db)
    service = UdemyProgressService(db)
    plan = db.query(UdemySubjectPlan).filter_by(subject_delivery_id=delivery.id, active=True).one()

    aggregate = tmp_path / 'SOF3032_aggregate.xlsx'
    _save_workbook(aggregate, [
        ['STT', 'Email', 'Name', 'Tiến độ hiện tại', 'Chậm tiến độ', 'Học kỳ', 'Block'],
        [1, 'student1@fpt.edu.vn', 'Sinh viên Một', 75, 'Yes', 'Summer 2026', 'Block 1'],
        [2, 'student2@fpt.edu.vn', 'Sinh viên Hai', '90%', 'No', 'Summer 2026', 'Block 1'],
    ])
    parsed = service.parse_path(aggregate, active_plan=plan)
    assert parsed['parser_format'] == 'aggregate'
    assert len(parsed['records']) == 2
    assert parsed['records'][0].progress_percent == 75

    legacy = tmp_path / 'SOF3032_raw.xlsx'
    headers = [f'Column {index}' for index in range(1, 26)]
    row1 = [''] * 25; row1[1] = 'Sinh viên Một'; row1[2] = 'student1@fpt.edu.vn'; row1[16] = 100
    row2 = [''] * 25; row2[1] = 'Sinh viên Một'; row2[2] = 'student1@fpt.edu.vn'; row2[16] = 50
    _save_workbook(legacy, [headers, row1, row2], title=False)
    parsed_legacy = service.parse_path(legacy, active_plan=plan)
    assert parsed_legacy['parser_format'] == 'legacy_25_item_rows'
    assert len(parsed_legacy['records']) == 1
    assert parsed_legacy['records'][0].progress_percent == 75
    assert parsed_legacy['records'][0].source_row_count == 2


def test_process_batch_matches_ap_roster_and_writes_error_report(tmp_path, monkeypatch):
    db = _session()
    delivery, subject = _seed(db)
    monkeypatch.setattr(settings, 'local_storage_path', str(tmp_path))
    import_dir = tmp_path / 'udemy-progress-imports' / 'job-1'
    import_dir.mkdir(parents=True)
    path = import_dir / 'SOF3032_report.xlsx'
    _save_workbook(path, [
        ['STT', 'Email', 'Name', 'Tiến độ hiện tại', 'Chậm tiến độ', 'Học kỳ', 'Block'],
        [1, 'student1@fpt.edu.vn', 'Sinh viên Một', 75, '', 'Summer 2026', 'Block 1'],
        [2, 'unknown@fpt.edu.vn', 'Chưa có AP', 95, '', 'Summer 2026', 'Block 1'],
        [3, 'bad-email', 'Email lỗi', 50, '', 'Summer 2026', 'Block 1'],
    ])
    raw = path.read_bytes()
    batch = UdemyProgressImportBatch(
        id='batch-1',
        subject_delivery_id=delivery.id,
        idempotency_key='delivery-sof3032:' + hashlib.sha256(raw).hexdigest(),
        file_name=path.name,
        file_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw),
        file_path=str(path),
        status='queued',
        requested_by='admin-1',
    )
    db.add(batch); db.commit()

    result = UdemyProgressService(db).process_batch(batch)
    assert result['matched_rows'] == 1
    assert result['unmatched_rows'] == 1
    assert result['failed_rows'] == 1
    assert result['late_rows'] == 1

    matched = db.query(UdemyStudentProgress).filter_by(subject_delivery_id=delivery.id, normalized_email='student1@fpt.edu.vn').one()
    assert matched.student_id == 'student-1'
    assert matched.class_id == 'class-sof3032-1'
    assert matched.match_status == 'matched_roster'
    assert matched.progress_percent == 75
    assert matched.required_progress_percent == 80
    assert matched.is_late is True

    unknown = db.query(UdemyStudentProgress).filter_by(subject_delivery_id=delivery.id, normalized_email='unknown@fpt.edu.vn').one()
    assert unknown.match_status == 'unmatched'
    assert db.query(UdemyProgressUnmatchedRow).filter_by(batch_id=batch.id).count() == 2
    db.refresh(batch)
    assert batch.status == 'completed'
    assert Path(batch.error_report_path).is_file()

    summary = UdemyProgressService(db).current_summary(delivery.id)
    assert summary['total_students'] == 2
    assert summary['matched_students'] == 1
    assert summary['unmatched_students'] == 1
    assert summary['late_students'] == 1

    listed = AcademicSubjectDeliveryService(db).list_deliveries(term_id='term-su26', block_id='block-1', branch='poly')
    item = listed['items'][0]
    assert item['last_udemy_import_at'] is not None
    assert item['udemy_progress_student_count'] == 2
    assert item['udemy_progress_late_count'] == 1
    assert item['udemy_progress_unmatched_count'] == 1


def test_batch33_cross_layer_contracts():
    model = (ROOT / 'backend/app/models/academic.py').read_text(encoding='utf-8')
    migration = (ROOT / 'backend/alembic/versions/0056_v25_9_16_7_2_64_33_udemy_progress.py').read_text(encoding='utf-8')
    service = (ROOT / 'backend/app/services/academic/udemy_progress.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    worker = (ROOT / 'backend/app/worker.py').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/app/subject-management/page.tsx').read_text(encoding='utf-8')
    dialog = (ROOT / 'frontend/components/subject-management/UdemyProgressImportDialog.tsx').read_text(encoding='utf-8')

    assert 'class UdemyProgressImportBatch' in model
    assert 'class UdemyStudentProgress' in model
    assert "down_revision = '0055_v25_9_16_7_2_64_32'" in migration
    assert 'legacy_25_item_rows' in service
    assert "@router.post('/udemy/progress/import/jobs'" in routes
    assert "@router.post('/udemy/progress/import-batches/{batch_id}/retry'" in routes
    assert "@celery_app.task(name='academic_udemy_progress_import_task')" in worker
    assert "'academic_udemy_progress_import_task': {'queue': 'exports'}" in worker
    assert 'Import điểm Udemy' in frontend
    assert 'Import lại có chủ đích' in dialog
    assert 'retryUdemyProgressImportBatch' in dialog
    assert 'getUdemyProgressImportBatches' in dialog
    assert 'edxkey.pem' not in '\n'.join(str(path) for path in ROOT.rglob('*'))
