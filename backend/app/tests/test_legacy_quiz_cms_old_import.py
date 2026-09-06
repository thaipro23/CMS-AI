from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from xml.etree import ElementTree as ET

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import audit, cost, course, job, question, question_bank, rbac  # noqa: F401
from app.models.question import Question, QuestionReviewLog
from app.models.question_bank import (
    BankReleaseQuestion,
    Department,
    LearningMaterialVersion,
    QuestionBankRelease,
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
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
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


def test_missing_difficulty_is_unclassified_instead_of_real_medium() -> None:
    raw = _workbook_bytes([
        {'question': 'Câu CMS cũ chưa có độ khó?', 'type': 0, 'correct': 'A'},
    ], include_threshold=False)
    parsed = parse_legacy_quiz_workbook(raw, filename='MEC004.xlsx')
    imported = parsed['sheets'][0]['questions'][0]
    assert imported['difficulty'] == 'medium'
    assert imported['difficulty_classified'] is False
    assert parsed['difficulty_counts'] == {'unclassified': 1}
    assert any('phân bổ linh hoạt khi tạo Quiz' in item for item in parsed['warnings'])


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


def test_bank_publish_preflight_failure_is_reported_before_import(monkeypatch) -> None:
    raw = _workbook_bytes([
        {'question': 'Câu hợp lệ về cấu trúc nhưng bị publish guard từ chối?', 'type': 0, 'threshold': 1, 'correct': 'A'},
    ])

    def reject_publish_contract(_question):
        raise ValueError('publish contract rejected')

    monkeypatch.setattr(
        'app.services.question_bank.legacy_quiz_import.validate_question_for_olx',
        reject_publish_contract,
    )
    parsed = parse_legacy_quiz_workbook(raw, filename='MEC005.xlsx')
    question = parsed['sheets'][0]['questions'][0]
    assert any(item['code'] == 'BANK_PREFLIGHT_FAILED' for item in question['errors'])
    assert any(item['code'] == 'BANK_PREFLIGHT_FAILED' for item in parsed['errors'])


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
    assert 'subjectDepartmentIds' in departments_source
    assert 'bank-subject-search-results' in departments_source
    import_page_source = (root / 'frontend/app/import-quiz-cms-old/page.tsx').read_text(
        encoding='utf-8'
    )
    assert 'Bổ sung ảnh và kiểm tra lại' in import_page_source
    assert 'Bỏ qua ${preview.invalid_question_count} câu lỗi' in import_page_source
    assert 'WorkspaceSection' in import_page_source
    assert 'errorGroups.length ? errorGroups.map' in import_page_source


def test_quiz_creation_contract_has_no_question_type_quota_and_spacing_is_scoped() -> None:
    root = Path(__file__).resolve().parents[3]
    runtime_paths = [
        root / 'backend/app/schemas/question_bank.py',
        root / 'backend/app/services/question_bank/quiz_creation.py',
        root / 'backend/app/worker.py',
        root / 'frontend/app/bank/quiz/page.tsx',
        root / 'frontend/lib/api.ts',
    ]
    forbidden = (
        'single_select_count',
        'multi_select_count',
        'text_input_count',
        'numerical_input_count',
        'question_type_target_counts',
        'question_type_coverage',
    )
    for path in runtime_paths:
        source = path.read_text(encoding='utf-8')
        for token in forbidden:
            assert token not in source, f'{token} vẫn còn trong runtime tạo Quiz: {path}'

    spacing = (root / 'frontend/styles/project-spacing-contract.css').read_text(encoding='utf-8')
    globals_css = (root / 'frontend/app/globals.css').read_text(encoding='utf-8')
    bank_css = (root / 'frontend/styles/bank-design-contract.css').read_text(encoding='utf-8')
    assert ':where(.enterprise-content.page-stack)' in spacing
    assert '!important' not in spacing
    assert '.page-stack, .bank-multipage, .enterprise-standard-page' not in spacing
    assert '.subject-quick-search' not in globals_css
    assert '.bank-departments-page .bank-subject-search-results' in bank_css


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
            {'question': 'Điền [_____] vào câu.', 'type': 2, 'correct': 'A'},
        ], include_threshold=False)
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
        assert imported.quality_flags == [
            'legacy_import_requires_review',
            'legacy_import_unclassified_concept',
            'legacy_import_unclassified_difficulty',
        ]
        assert '"difficulty_classified":false' in imported.source_evidence
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


def test_quiz_planner_relaxes_concept_and_difficulty_only_for_legacy_imports() -> None:
    db = _session()
    try:
        release = QuestionBankRelease(
            id='release-flexible-legacy',
            bank_version_id='version-flexible-legacy',
            subject_id='subject-flexible-legacy',
            chapter_id='chapter-flexible-legacy',
            release_code='MEC004-SU26-B1-v1',
            status='published',
            openedx_library_key='lib:FPT:mec004-su26-b1-v1',
            metadata_json={'verification_complete': True},
        )
        db.add(release)
        for index in range(5):
            question_id = f'legacy-unclassified-{index}'
            imported = Question(
                id=question_id,
                course_id='bank:version-flexible-legacy',
                bank_version_id='version-flexible-legacy',
                difficulty='medium',
                learning_objective='',
                question_text=f'Câu CMS cũ {index + 1}?',
                option_a='Đúng',
                option_b='Sai',
                option_c='',
                option_d='',
                correct_answer='A',
                question_type='multi_select' if index % 2 else 'single_select',
                source_type='legacy_quiz_excel',
                source_evidence=(
                    '{"difficulty_classified":false,"threshold_raw":"",'
                    '"difficulty_raw":""}'
                ),
                quality_flags=[
                    'legacy_import_requires_review',
                    'legacy_import_unclassified_concept',
                    'legacy_import_unclassified_difficulty',
                ],
                status='published',
            )
            db.add(imported)
            db.add(BankReleaseQuestion(
                bank_release_id=release.id,
                question_id=question_id,
                question_family_id=None,
                difficulty='medium',
                openedx_library_problem_id=f'lb:problem:{question_id}',
            ))
        db.commit()

        workflow = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))
        plan = workflow._build_release_quiz_plan(
            release=release,
            total_questions=3,
            difficulty_easy=34,
            difficulty_medium=33,
            difficulty_hard=33,
        )
        assert plan['classification_policy'] == 'legacy_flexible_fallback'
        assert plan['unclassified_difficulty_question_count'] == 5
        assert plan['unclassified_concept_question_count'] == 5
        assert plan['flexibly_assigned_question_count'] == 5
        assert plan['target_counts'] == {'EASY': 1, 'MEDIUM': 1, 'HARD': 1}
        assert len(plan['slots']) == 3
        assigned = [question_id for slot in plan['slots'] for question_id in slot['question_ids']]
        assert len(assigned) == len(set(assigned)) == 5
        assert all(
            family['unclassified_concept']
            for slot in plan['slots']
            for family in slot['families']
        )

        strict_release = QuestionBankRelease(
            id='release-strict-manual',
            bank_version_id='version-strict-manual',
            subject_id='subject-strict-manual',
            chapter_id='chapter-strict-manual',
            release_code='MEC004-SU26-B2-v1',
            status='published',
            openedx_library_key='lib:FPT:mec004-su26-b2-v1',
            metadata_json={'verification_complete': True},
        )
        strict_question = Question(
            id='manual-medium-no-concept',
            course_id='bank:version-strict-manual',
            bank_version_id='version-strict-manual',
            difficulty='medium',
            learning_objective='',
            question_text='Câu tạo tay không có concept?',
            option_a='Đúng',
            option_b='Sai',
            option_c='',
            option_d='',
            correct_answer='A',
            question_type='single_select',
            source_type='manual',
            status='published',
        )
        db.add_all([
            strict_release,
            strict_question,
            BankReleaseQuestion(
                bank_release_id=strict_release.id,
                question_id=strict_question.id,
                difficulty='medium',
                openedx_library_problem_id='lb:problem:manual-medium-no-concept',
            ),
        ])
        db.commit()
        with pytest.raises(ValueError, match='không đủ câu theo độ khó'):
            workflow._build_release_quiz_plan(
                release=strict_release,
                total_questions=1,
                difficulty_easy=100,
                difficulty_medium=0,
                difficulty_hard=0,
            )
    finally:
        db.close()


@pytest.mark.parametrize('assessment_type', ['quiz', 'final_test'])
def test_legacy_quiz_rebalances_missing_hard_without_question_type_quota(assessment_type: str) -> None:
    db = _session()
    try:
        release = QuestionBankRelease(
            id='release-legacy-mixed-types-no-hard',
            bank_version_id='version-legacy-mixed-types-no-hard',
            subject_id='subject-legacy-mixed-types-no-hard',
            chapter_id='chapter-legacy-mixed-types-no-hard',
            release_code='AUT218-FA26-B1-v1',
            status='published',
            openedx_library_key='lib:FPT:aut218-fa26-b1-v1',
            metadata_json={'verification_complete': True},
        )
        db.add(release)
        for index in range(18):
            difficulty = 'easy' if index < 12 else 'medium'
            question_id = f'legacy-mixed-no-hard-{index}'
            db.add(Question(
                id=question_id,
                course_id='bank:version-legacy-mixed-types-no-hard',
                bank_version_id='version-legacy-mixed-types-no-hard',
                difficulty=difficulty,
                learning_objective=f'LO {index + 1}',
                topic=f'Chủ đề {index + 1}',
                question_text=f'Câu legacy hỗn hợp {index + 1}?',
                option_a='Đúng',
                option_b='Sai',
                option_c='',
                option_d='',
                correct_answer='A' if index % 3 else 'AB',
                question_type='multi_select' if index % 3 == 0 else 'single_select',
                source_type='legacy_quiz_excel',
                source_evidence='{"difficulty_classified":true,"threshold_raw":"1"}',
                status='published',
            ))
            db.add(BankReleaseQuestion(
                bank_release_id=release.id,
                question_id=question_id,
                difficulty=difficulty,
                openedx_library_problem_id=f'lb:problem:{question_id}',
            ))
        db.commit()

        workflow = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))
        config = dict(total_questions=15, difficulty_easy=50, difficulty_medium=30, difficulty_hard=20)
        if assessment_type == 'final_test':
            plan = workflow._build_final_test_plan(source_releases=[release], source_details=[], **config)
        else:
            plan = workflow._build_release_quiz_plan(release=release, **config)

        assert plan['target_counts'] == {'EASY': 7, 'MEDIUM': 5, 'HARD': 3}
        assert plan['effective_target_counts'] == {'EASY': 9, 'MEDIUM': 6, 'HARD': 0}
        if assessment_type == 'quiz':
            assert len(plan['slots']) == 15
        assert sum(int(slot['pick_count']) for slot in plan['slots']) == 15
        assigned_ids = {
            question_id
            for slot in plan['slots']
            for question_id in slot['question_ids']
        }
        assigned_types = {
            db.get(Question, question_id).question_type
            for question_id in assigned_ids
        }
        assert assigned_types == {'single_select', 'multi_select'}
        assert 'question_type_target_counts' not in plan
        assert any('tự cân lại' in warning for warning in plan['warnings'])
    finally:
        db.close()


@pytest.mark.parametrize(('config', 'expected'), [
    ({'difficulty_easy': 100, 'difficulty_medium': 0, 'difficulty_hard': 0, 'retake_cooldown_minutes': 0}, (100, 0, 0, 0)),
    ({'difficulty_easy': 0, 'difficulty_medium': 100, 'difficulty_hard': 0, 'retake_cooldown_minutes': 0}, (0, 100, 0, 0)),
    ({'difficulty_easy': 0, 'difficulty_medium': 0, 'difficulty_hard': 100, 'retake_cooldown_minutes': 0}, (0, 0, 100, 0)),
    ({}, (50, 30, 20, 5)),
    ({'difficulty_easy': None, 'difficulty_medium': None, 'difficulty_hard': None, 'retake_cooldown_minutes': None}, (50, 30, 20, 5)),
])
def test_quiz_worker_preserves_zero_values_and_defaults(monkeypatch, config: dict, expected: tuple) -> None:
    from app import worker
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService

    db = Mock()
    job = SimpleNamespace(id='quiz-job', request_json=config, requested_by=None, release_id='release-1')
    ops = Mock()
    ops.get_job.return_value = job
    ops.complete.side_effect = lambda job, *, result, label: SimpleNamespace(result_json=result)
    create_quiz = AsyncMock(return_value={'ok': True, 'status': 'completed'})
    monkeypatch.setattr(worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(BankOperationJobService, '__new__', lambda cls, db: ops)
    monkeypatch.setattr(VersionedQuestionBankService, 'create_quiz_from_release', create_quiz)
    monkeypatch.setattr('app.services.audit_log.log_audit', Mock())

    result = worker.bank_quiz_create_task.run(job.id)

    assert result['ok'] is True
    create_quiz.assert_awaited_once()
    sent = create_quiz.await_args.kwargs
    assert tuple(sent[key] for key in (
        'difficulty_easy', 'difficulty_medium', 'difficulty_hard', 'retake_cooldown_minutes',
    )) == expected
    ops.fail.assert_not_called()
    db.close.assert_called_once()
