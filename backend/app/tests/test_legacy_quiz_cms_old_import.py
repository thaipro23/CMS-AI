from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import audit, cost, course, job, question, question_bank, rbac  # noqa: F401
from app.models.question import Question, QuestionReviewLog
from app.models.question_bank import (
    Department,
    LearningMaterialVersion,
    Subject,
    SubjectOffering,
)
from app.services.object_storage import ObjectStorage
from app.services.openedx_exporter import question_to_openedx_olx, validate_question_for_olx
from app.services.question_bank.legacy_quiz_import import (
    build_legacy_quiz_preview,
    discard_invalid_legacy_quiz_questions,
    import_legacy_quiz_preview,
    load_legacy_quiz_preview,
    parse_legacy_quiz_workbook,
    persist_legacy_quiz_preview,
    public_legacy_quiz_preview,
    replace_legacy_quiz_preview,
)
from app.services.question_content import apply_canonical_content


def _workbook_bytes(
    questions: list[dict],
    *,
    include_type: bool = True,
    include_threshold: bool = True,
    sheet_name: str = 'Quiz 01',
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    headers = ['NO', 'QUESTION', 'ABC', 'ANSWER', 'CORRECT']
    if include_type:
        headers.append('TYPE')
    if include_threshold:
        headers.append('NGƯỠNG')
    worksheet.append(headers)
    for number, item in enumerate(questions, start=1):
        options = item.get('options') or ['A one', 'B two', 'C three', 'D four']
        for option_index, option in enumerate(options):
            row = [
                number if option_index == 0 else None,
                item['question'] if option_index == 0 else None,
                chr(ord('A') + option_index),
                option,
                item.get('correct', 'A') if option_index == len(options) - 1 else None,
            ]
            if include_type:
                row.append(item.get('type') if option_index == 0 else None)
            if include_threshold:
                row.append(item.get('threshold') if option_index == 0 else None)
            worksheet.append(row)
    from io import BytesIO

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _storage(tmp_path: Path) -> ObjectStorage:
    return ObjectStorage(SimpleNamespace(storage_provider='local', local_storage_path=str(tmp_path)))


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.new('RGB', (2, 2), color=(20, 80, 160)).save(output, format='PNG')
    return output.getvalue()


def test_type_and_threshold_are_independent_columns() -> None:
    raw = _workbook_bytes([
        {'question': 'Một đáp án?', 'type': 0, 'threshold': 3, 'correct': 'A'},
        {'question': 'Nhiều đáp án?', 'type': 1, 'threshold': 1, 'correct': 'AC'},
        {'question': 'Điền [_____] rồi [_____].', 'type': 2, 'threshold': 2, 'correct': 'AB'},
    ])
    parsed = parse_legacy_quiz_workbook(raw, filename='MEC001 - demo.xlsx')
    questions = parsed['sheets'][0]['questions']
    assert [(item['question_type'], item['difficulty']) for item in questions] == [
        ('single_select', 'hard'),
        ('multi_select', 'easy'),
        ('dropdown_fill', 'medium'),
    ]
    assert not parsed['errors']


def test_missing_type_is_inferred_from_correct_key() -> None:
    raw = _workbook_bytes([
        {'question': 'Câu đơn?', 'correct': 'B', 'threshold': 1},
        {'question': 'Câu nhiều?', 'correct': 'BD', 'threshold': 2},
    ], include_type=False)
    parsed = parse_legacy_quiz_workbook(raw, filename='MEC002.xlsx')
    assert parsed['type_counts'] == {'single_select': 1, 'multi_select': 1}
    assert parsed['difficulty_counts'] == {'easy': 1, 'medium': 1}


def test_duplicate_prompts_are_warnings_and_preserved() -> None:
    raw = _workbook_bytes([
        {'question': 'Nội dung bị lặp?', 'type': 0, 'threshold': 1},
        {'question': 'Nội dung bị lặp?', 'type': 0, 'threshold': 2},
    ])
    parsed = parse_legacy_quiz_workbook(raw, filename='MEC003.xlsx')
    questions = parsed['sheets'][0]['questions']
    assert parsed['question_count'] == 2
    assert not parsed['errors']
    assert all(item['duplicate_in_source'] for item in questions)
    assert any('vẫn giữ từng dòng' in warning for warning in parsed['warnings'])


def test_missing_image_requires_upload_or_explicit_question_discard(tmp_path: Path) -> None:
    db = _session()
    storage = _storage(tmp_path)
    try:
        department = Department(code='MEC', name='Cơ khí', status='active')
        db.add(department)
        db.flush()
        subject = Subject(
            department_id=department.id,
            code='MEC229',
            name='Đồ gá',
            status='active',
        )
        db.add(subject)
        db.commit()
        raw = _workbook_bytes([
            {'question': '[QN12.png] Câu có hình?', 'type': 0, 'threshold': 2},
            {'question': 'Câu hợp lệ không có hình?', 'type': 0, 'threshold': 1},
        ])
        missing = build_legacy_quiz_preview(
            db,
            workbooks=[('MEC229 - Đồ gá.xlsx', raw)],
            visible_subject_ids={subject.id},
            actor='teacher@example.com',
        )
        assert not missing['can_commit']
        assert {item['code'] for item in missing['errors']} == {'MISSING_IMAGE'}
        public_missing = public_legacy_quiz_preview(missing)
        assert public_missing['invalid_question_count'] == 1
        assert public_missing['missing_image_question_count'] == 1
        assert public_missing['can_skip_invalid_questions']

        completed_with_image = build_legacy_quiz_preview(
            db,
            workbooks=[('MEC229 - Đồ gá.xlsx', raw)],
            assets=[('QN12.png', _png_bytes())],
            visible_subject_ids={subject.id},
            actor='teacher@example.com',
        )
        assert completed_with_image['can_commit']
        assert public_legacy_quiz_preview(completed_with_image)[
            'missing_image_question_count'
        ] == 0
        assert completed_with_image['image_count'] == 1

        token, _reference = persist_legacy_quiz_preview(missing, storage=storage)
        stored = load_legacy_quiz_preview(token, storage=storage)
        filtered = discard_invalid_legacy_quiz_questions(stored)
        assert filtered['can_commit']
        assert filtered['question_count'] == 1
        assert filtered['skipped_invalid_question_count'] == 1
        assert not filtered['errors']
        assert filtered['workbooks'][0]['sheets'][0]['question_count'] == 1
        replace_legacy_quiz_preview(token, filtered, storage=storage)
        reloaded = load_legacy_quiz_preview(token, storage=storage)
        assert reloaded['can_commit']
        assert reloaded['skipped_invalid_questions'][0]['image_refs'] == ['QN12.png']

        imported = import_legacy_quiz_preview(
            db,
            preview_token=token,
            actor='teacher@example.com',
            storage=storage,
        )
        assert imported['created_question_count'] == 1
        assert imported['skipped_invalid_question_count'] == 1
        assert db.query(Question).one().question_text == 'Câu hợp lệ không có hình?'

        unknown = build_legacy_quiz_preview(
            db,
            workbooks=[('UNKNOWN - Đồ gá.xlsx', raw)],
            visible_subject_ids={subject.id},
            actor='teacher@example.com',
        )
        filtered_unknown = discard_invalid_legacy_quiz_questions(unknown)
        assert not filtered_unknown['can_commit']
        assert {item['code'] for item in filtered_unknown['errors']} == {'SUBJECT_NOT_FOUND'}
    finally:
        db.close()


def test_dropdown_olx_keeps_order_and_rejects_blank_mismatch() -> None:
    question_model = Question(
        course_id='bank:test',
        difficulty='medium',
        question_text='Chọn [_____] trước [_____].',
        option_a='',
        option_b='',
        option_c='',
        option_d='',
        correct_answer='A',
        explanation='Theo đúng thứ tự.',
        status='pending_review',
    )
    content = {
        'response': {
            'type': 'dropdown_fill',
            'options': [
                {'id': 'opt-a', 'text': 'pha chế', 'feedback': ''},
                {'id': 'opt-b', 'text': 'phục vụ', 'feedback': ''},
                {'id': 'opt-c', 'text': 'thu ngân', 'feedback': ''},
            ],
            'correct_option_ids': ['opt-b', 'opt-a'],
        },
    }
    apply_canonical_content(question_model, 'dropdown_fill', content)
    olx = question_to_openedx_olx(question_model)
    ET.fromstring(olx)
    assert olx.count('<optionresponse inline="1">') == 2
    assert olx.count('<solution>') == 1
    first_response, second_response = olx.split('<optionresponse inline="1">')[1:]
    assert '<option correct="true">phục vụ</option>' in first_response
    assert '<option correct="true">pha chế</option>' in second_response

    question_model.question_text = 'Chỉ có [_____].'
    with pytest.raises(ValueError, match='Số ô trống'):
        validate_question_for_olx(question_model)


def test_cross_layer_contract_contains_route_type_and_navigation() -> None:
    root = Path(__file__).resolve().parents[3]
    route_source = (root / 'backend/app/api/routes/question_bank_v2.py').read_text(encoding='utf-8')
    worker_source = (root / 'backend/app/worker.py').read_text(encoding='utf-8')
    types_source = (root / 'frontend/types/index.ts').read_text(encoding='utf-8')
    shell_source = (root / 'frontend/components/layout/AppShell.tsx').read_text(encoding='utf-8')
    departments_source = (
        root / 'frontend/app/bank/_components/pages/DepartmentsPage.tsx'
    ).read_text(encoding='utf-8')
    assert "'/import-quiz-cms-old/preview'" in route_source
    assert "'/import-quiz-cms-old/skip-errors'" in route_source
    assert "'/import-quiz-cms-old/jobs'" in route_source
    assert "name='bank_legacy_quiz_import_task'" in worker_source
    assert "'dropdown_fill'" in types_source
    assert "href: '/import-quiz-cms-old'" in shell_source
    assert 'searchSubjects(headers' in departments_source
    assert '}, 250)' in departments_source
    assert '/bank/subjects/${subject.id}/versions' in departments_source
    import_page_source = (root / 'frontend/app/import-quiz-cms-old/page.tsx').read_text(
        encoding='utf-8'
    )
    assert 'Bổ sung ảnh và kiểm tra lại' in import_page_source
    assert 'Bỏ qua ${preview.invalid_question_count} câu lỗi' in import_page_source


def test_end_to_end_import_creates_su26_audit_and_is_retry_idempotent(tmp_path: Path) -> None:
    db = _session()
    storage = _storage(tmp_path)
    try:
        department = Department(code='HOS', name='Du lịch', status='active')
        db.add(department)
        db.flush()
        subject = Subject(
            department_id=department.id,
            code='HOS2032',
            name='Nghiệp vụ Bar',
            status='active',
        )
        db.add(subject)
        db.commit()
        raw = _workbook_bytes([
            {'question': 'Điền [_____] vào câu.', 'type': 2, 'correct': 'A', 'threshold': 2},
        ])
        preview = build_legacy_quiz_preview(
            db,
            workbooks=[('HOS2032 - Nghiệp vụ Bar.xlsx', raw)],
            visible_subject_ids={subject.id},
            actor='importer@example.com',
        )
        assert preview['can_commit']
        token, _reference = persist_legacy_quiz_preview(preview, storage=storage)

        first = import_legacy_quiz_preview(
            db,
            preview_token=token,
            actor='importer@example.com',
            storage=storage,
            cleanup_preview=False,
        )
        assert first['created_question_count'] == 1
        imported = db.query(Question).one()
        assert imported.status == 'pending_review'
        assert imported.created_by == 'importer@example.com'
        assert imported.question_type == 'dropdown_fill'
        assert imported.quality_flags == ['legacy_import_requires_review']
        assert db.query(QuestionReviewLog).filter_by(
            question_id=imported.id,
            actor='importer@example.com',
            new_status='pending_review',
        ).count() == 1
        offering = db.query(SubjectOffering).one()
        assert offering.code == 'HOS2032_SU26'
        assert offering.term == 'SU26'
        material = db.query(LearningMaterialVersion).one()
        assert material.change_type == 'legacy_quiz_import'
        assert material.uploaded_by == 'importer@example.com'

        second = import_legacy_quiz_preview(
            db,
            preview_token=token,
            actor='importer@example.com',
            storage=storage,
            cleanup_preview=False,
        )
        assert second['created_question_count'] == 0
        assert second['skipped_question_count'] == 1
        assert db.query(Question).count() == 1
        assert db.query(LearningMaterialVersion).count() == 1
    finally:
        db.close()
