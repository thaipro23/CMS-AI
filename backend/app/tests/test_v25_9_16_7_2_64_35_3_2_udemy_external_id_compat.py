from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from app.services.academic.udemy_progress import UdemyProgressService


UDEMY_HEADERS_26 = [
    'Tên của người dùng',
    'Họ của người dùng',
    'Email của người dùng',
    'Nhóm người dùng',
    'Người dùng bị hủy kích hoạt',
    'ID bên ngoài',
    'Loại giấy phép',
    'ID lộ trình',
    'Tiêu đề lộ trình',
    'Biên tập viên lộ trình',
    'ID phần của mục',
    'Tiêu đề phần của mục',
    'ID mục trong lộ trình',
    'Loại đối tượng của mục trong lộ trình',
    'ID đối tượng của mục trong lộ trình',
    'Tiêu đề của mục trong lộ trình',
    'Thời lượng của mục trong lộ trình',
    'Tỷ lệ hoàn thành mục trong lộ trình',
    'Video đã xem của mục trong lộ trình',
    'Ngày ghi danh của mục trong lộ trình',
    'Ngày hoạt động đầu tiên của mục trong lộ trình',
    'Ngày hoạt động gần đây nhất của mục trong lộ trình',
    'Ngày hoàn thành đầu tiên của mục trong lộ trình',
    'Ngày hoàn thành mục trong lộ trình',
    'Số ngày hoạt động',
    'Thể loại con của mục trong lộ trình',
]


def _row(email: str = 'student@fpt.edu.vn', progress: str | int = 50) -> list[object]:
    row: list[object] = [''] * len(UDEMY_HEADERS_26)
    row[0] = 'Nguyễn Văn'
    row[1] = 'A'
    row[2] = email
    row[5] = 'external-id-that-must-be-ignored'
    row[17] = progress
    return row


def test_batch35_3_2_maps_current_udemy_vietnamese_header_by_name():
    row_no, columns, parser_format = UdemyProgressService._find_header_rows([UDEMY_HEADERS_26])
    assert row_no == 1
    assert columns['email'] == 3
    assert columns['progress'] == 18
    assert parser_format == 'item_rows'


def test_batch35_3_2_accepts_csv_metadata_and_external_id_column(tmp_path: Path):
    path = tmp_path / 'SOF3032_report.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(UDEMY_HEADERS_26)
        writer.writerow(_row(progress=50))

    UdemyProgressService.validate_upload_metadata(filename=path.name, content_type='text/csv')
    raw = path.read_bytes()
    UdemyProgressService.validate_upload_content(filename=path.name, raw=raw)
    parsed = UdemyProgressService(None).parse_path(path, active_plan=SimpleNamespace(item_count=1))

    assert parsed['parser_format'] == 'item_rows'
    assert len(parsed['records']) == 1
    assert parsed['records'][0].normalized_email == 'student@fpt.edu.vn'
    assert parsed['records'][0].progress_percent == 50.0


def test_batch35_3_2_xlsx_is_header_based_even_when_external_id_moves(tmp_path: Path):
    headers = list(UDEMY_HEADERS_26)
    external = headers.pop(headers.index('ID bên ngoài'))
    headers.append(external)
    values = {name: '' for name in headers}
    values['Tên của người dùng'] = 'Nguyễn Văn'
    values['Họ của người dùng'] = 'A'
    values['Email của người dùng'] = 'moved@fpt.edu.vn'
    values['Tỷ lệ hoàn thành mục trong lộ trình'] = 75
    values['ID bên ngoài'] = 'moved-column'

    path = tmp_path / 'SOF3032_report.xlsx'
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append([values[name] for name in headers])
    wb.save(path)
    wb.close()

    parsed = UdemyProgressService(None).parse_path(path, active_plan=SimpleNamespace(item_count=1))
    assert len(parsed['records']) == 1
    assert parsed['records'][0].normalized_email == 'moved@fpt.edu.vn'
    assert parsed['records'][0].progress_percent == 75.0


def test_batch35_3_2_legacy_25_column_fallback_remains_available():
    unknown_header = [f'column-{index}' for index in range(25)]
    row_no, columns, parser_format = UdemyProgressService._find_header_rows([unknown_header])
    assert row_no == 1
    assert columns == {'email': 3, 'name': 2, 'progress': 17}
    assert parser_format == 'legacy_25_item_rows'
