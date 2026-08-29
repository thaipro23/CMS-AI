from __future__ import annotations

from pathlib import Path


def test_ap_runtime_contains_no_apitest_or_remote_campus_catalog():
    root = Path(__file__).resolve().parents[3]
    runtime_paths = [
        root / 'backend/app',
        root / 'frontend/app',
        root / 'frontend/lib',
    ]
    offenders: list[str] = []
    for base in runtime_paths:
        for path in base.rglob('*'):
            if path.suffix not in {'.py', '.ts', '.tsx'}:
                continue
            if 'tests' in path.parts:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore').lower()
            if 'apitest.poly.edu.vn' in text or '/api/cms/get-campus' in text:
                offenders.append(str(path.relative_to(root)))

    assert offenders == []


def test_all_frontend_tables_with_stt_header_render_stt_cell():
    root = Path(__file__).resolve().parents[3] / 'frontend'
    offenders: list[str] = []
    for path in root.rglob('*.tsx'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        start = 0
        while True:
            table_start = text.find('<table', start)
            if table_start < 0:
                break
            table_end = text.find('</table>', table_start)
            if table_end < 0:
                break
            block = text[table_start:table_end + len('</table>')]
            line_no = text[:table_start].count('\n') + 1
            has_stt_header = '<th>STT' in block or '<th className="stt' in block
            if has_stt_header and 'stt-cell' not in block:
                offenders.append(f'{path.relative_to(root.parent)}:{line_no}')
            start = table_end + len('</table>')

    assert offenders == []
