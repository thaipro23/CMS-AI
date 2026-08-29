from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.models.academic import AcademicTerm
from app.services.academic.udemy_progress import UdemyProgressService

ROOT = Path(__file__).resolve().parents[3]


def _udemy_csv(*, subject: str, term: str, email: str = 'student@fpt.edu.vn') -> bytes:
    text = (
        'Tên của người dùng,Họ của người dùng,Email của người dùng,Nhóm người dùng,Người dùng bị hủy kích hoạt,ID bên ngoài,Loại giấy phép,ID lộ trình,Tiêu đề lộ trình,Tỷ lệ hoàn thành mục trong lộ trình\n'
        f'Sinh viên,,{email},,Không,,Doanh nghiệp,123,Poly - {subject} - Môn thử nghiệm_{term},50\n'
    )
    return text.encode('utf-8-sig')


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    raw = BytesIO()
    with ZipFile(raw, 'w', ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return raw.getvalue()


def test_batch35_3_3_zip_expands_many_reports_and_reports_unsupported_members():
    raw = _zip_bytes({
        'SOF3032_path_user_item_activity_report.csv': _udemy_csv(subject='SOF3032', term='SU2026'),
        'WEB2055_path_user_item_activity_report.csv': _udemy_csv(subject='WEB2055', term='SU2026'),
        'readme.txt': b'not a report',
    })
    members, rejected = UdemyProgressService.expand_upload_payload(
        filename='Udemy_11.8.zip',
        content_type='application/zip',
        raw=raw,
    )
    assert [item['filename'] for item in members] == [
        'SOF3032_path_user_item_activity_report.csv',
        'WEB2055_path_user_item_activity_report.csv',
    ]
    assert len(rejected) == 1
    assert rejected[0]['reason_code'] == 'UNSUPPORTED_FILE'
    for item in members:
        UdemyProgressService.validate_upload_content(filename=item['filename'], raw=item['raw'])


def test_batch35_3_3_zip_rejects_path_traversal():
    raw = _zip_bytes({'../escape.csv': _udemy_csv(subject='SOF3032', term='SU2026')})
    with pytest.raises(ValueError, match='đường dẫn nội bộ'):
        UdemyProgressService.expand_upload_payload(
            filename='unsafe.zip',
            content_type='application/zip',
            raw=raw,
        )


def test_batch35_3_3_report_identity_detects_subject_term_and_branch():
    identity = UdemyProgressService.inspect_report_identity(
        filename='PRE2041_path_user_item_activity_report.csv',
        raw=_udemy_csv(subject='PRE2041', term='SP2026'),
    )
    assert identity['subject_code'] == 'PRE2041'
    assert identity['term_code'] == 'SP2026'
    assert identity['branch'] == 'poly'


def test_batch35_3_3_term_alias_supports_ap_short_code():
    term = AcademicTerm(term_code='SU26', term_name='Summer 2026', branch='poly', active=True)
    assert {'SU26', 'SU2026'} <= UdemyProgressService.expected_term_tokens(term)


def test_batch35_3_3_filename_vs_report_mismatch_can_be_detected_before_import():
    filename_code = UdemyProgressService.subject_code_from_filename('DAT115_path_user_item_activity_report.csv')
    identity = UdemyProgressService.inspect_report_identity(
        filename='DAT115_path_user_item_activity_report.csv',
        raw=_udemy_csv(subject='DAT110', term='SU2026'),
    )
    assert filename_code == 'DAT115'
    assert identity['subject_code'] == 'DAT110'
    assert filename_code != identity['subject_code']


def test_batch35_3_3_cross_layer_bulk_zip_contract():
    service = (ROOT / 'backend/app/services/academic/udemy_progress.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    worker = (ROOT / 'backend/app/worker.py').read_text(encoding='utf-8')
    schema = (ROOT / 'backend/app/schemas/academic.py').read_text(encoding='utf-8')
    dialog = (ROOT / 'frontend/components/subject-management/UdemyProgressImportDialog.tsx').read_text(encoding='utf-8')
    student_page = (ROOT / 'frontend/app/student-management/StudentManagementPlatformPage.tsx').read_text(encoding='utf-8')
    subject_page = (ROOT / 'frontend/app/subject-management/page.tsx').read_text(encoding='utf-8')
    config = (ROOT / 'backend/app/core/config.py').read_text(encoding='utf-8')

    assert "ARCHIVE_EXTENSIONS = {'.zip'}" in service
    assert 'expand_upload_payload' in service
    assert 'inspect_report_identity' in service
    assert 'SUBJECT_CODE_MISMATCH' in routes
    assert 'TERM_MISMATCH' in routes
    assert "'rejected_files': rejected_files" in routes
    assert "rejected_files = list(request.get('rejected_files') or [])" in worker
    assert 'class UdemyProgressImportRejectedFileOut' in schema
    assert 'rejected_count: int = 0' in schema
    assert 'getAcademicBlocks' in dialog
    assert '.zip' in dialog
    assert 'Import hàng loạt Udemy' in dialog
    assert 'Import hàng loạt Udemy' in student_page
    assert 'Import hàng loạt Udemy' in subject_page
    assert "app_version: str = '25.9.16.7.2.64.16.5.7.2.18'" in config
    assert not (ROOT / 'backend/alembic/versions/0058_v25_9_16_7_2_64_35_3_3_udemy_bulk_zip.py').exists()
