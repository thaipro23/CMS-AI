from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.errors import public_http_exception


def _mapped(active: Exception, *, status_code: int = 400, code: str = 'BANK_OPERATION_FAILED') -> HTTPException:
    try:
        raise active
    except Exception:
        return public_http_exception(
            status_code=status_code,
            code=code,
            message='Không thể hoàn tất thao tác.',
            logger_name=__name__,
        )


def test_public_error_mapping_preserves_domain_http_exception() -> None:
    original = HTTPException(status_code=404, detail={'code': 'NOT_FOUND', 'message': 'Không tìm thấy bản ghi'})
    mapped = _mapped(original)
    assert mapped is original
    assert mapped.status_code == 404
    assert mapped.detail['code'] == 'NOT_FOUND'


def test_public_error_mapping_keeps_domain_validation_reason() -> None:
    mapped = _mapped(ValueError('Mã bộ môn đã tồn tại'))
    assert mapped.status_code == 409
    assert mapped.detail == {'code': 'BANK_OPERATION_CONFLICT', 'message': 'Mã bộ môn đã tồn tại'}




def test_public_error_mapping_marks_missing_domain_entity_as_404() -> None:
    mapped = _mapped(ValueError('Không tìm thấy phiên bản môn'))
    assert mapped.status_code == 404
    assert mapped.detail == {
        'code': 'BANK_OPERATION_NOT_FOUND',
        'message': 'Không tìm thấy phiên bản môn',
    }


def test_public_error_mapping_reports_integrity_conflict_truthfully() -> None:
    mapped = _mapped(IntegrityError('insert', {}, Exception('duplicate key')))
    assert mapped.status_code == 409
    assert mapped.detail['code'] == 'BANK_OPERATION_CONFLICT'


def test_public_error_mapping_does_not_disguise_backend_defect_as_400() -> None:
    mapped = _mapped(NameError('SequenceMatcher is not defined'))
    assert mapped.status_code == 500
    assert mapped.detail['code'] == 'BANK_OPERATION_INTERNAL_ERROR'




def test_unhandled_exception_handler_keeps_json_error_envelope() -> None:
    import asyncio
    import json
    from types import SimpleNamespace

    from app.core.errors import unhandled_exception_handler

    request = SimpleNamespace(
        state=SimpleNamespace(request_id='request-contract-500'),
        headers={},
        url=SimpleNamespace(path='/api/contract-failure'),
    )
    response = asyncio.run(unhandled_exception_handler(request, RuntimeError('private backend detail')))
    payload = json.loads(response.body)
    assert response.status_code == 500
    assert payload['error']['code'] == 'INTERNAL_SERVER_ERROR'
    assert payload['error']['request_id'] == 'request-contract-500'
    assert 'private backend detail' not in payload['error']['message']


def test_frontend_api_client_adds_json_contract_and_preserves_backend_error_code() -> None:
    source = open('../frontend/lib/api.ts', encoding='utf-8').read()
    assert 'isLikelyJsonRequestBody' in source
    assert 'headers.set("Content-Type", "application/json")' in source
    assert 'code: apiErrorCode(data, `HTTP_${response.status}`)' in source
    assert 'details: apiErrorDetails(data)' in source
    assert 'validationDetailsMessage(details)' in source


def _bank_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.session import Base
    from app.models import audit, cost, course, job, question, question_bank, rbac  # noqa: F401

    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_hierarchy_create_validates_parent_and_duplicates_before_commit() -> None:
    from app.services.question_bank_service import VersionedQuestionBankService

    db = _bank_session()
    try:
        service = VersionedQuestionBankService(db)
        department = service.create_department(code='cntt', name='Công nghệ thông tin')
        assert department.code == 'CNTT'

        try:
            service.create_department(code=' CNTT ', name='Trùng mã')
            raise AssertionError('duplicate department code must fail')
        except ValueError as exc:
            assert str(exc) == 'Mã bộ môn đã tồn tại'
        assert db.is_active

        try:
            service.create_subject(department_id='missing', code='COM1071', name='Tin học 1')
            raise AssertionError('missing department must fail')
        except ValueError as exc:
            assert str(exc) == 'Không tìm thấy bộ môn'
        assert db.is_active

        subject = service.create_subject(
            department_id=department.id,
            code='com1071',
            name='Tin học 1',
        )
        try:
            service.create_subject(
                department_id=department.id,
                code=' COM1071 ',
                name='Môn trùng',
            )
            raise AssertionError('duplicate subject code must fail')
        except ValueError as exc:
            assert str(exc) == 'Mã môn đã tồn tại trong bộ môn này'
        assert db.is_active

        chapter = service.create_chapter(subject_id=subject.id, title='Bài 1', chapter_no=1)
        assert chapter.chapter_no == 1
        try:
            service.create_chapter(subject_id=subject.id, title='Bài 1 khác', chapter_no=1)
            raise AssertionError('duplicate chapter number must fail')
        except ValueError as exc:
            assert str(exc) == 'Bài số 1 đã tồn tại trong phiên bản môn này'
        assert db.is_active
    finally:
        db.close()


def test_broad_backend_exceptions_are_not_flattened_to_direct_http_400() -> None:
    import ast
    from pathlib import Path

    offenders: list[str] = []
    backend_root = Path(__file__).resolve().parents[2]
    for path in backend_root.rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
            is_broad = handler.type is None or (
                isinstance(handler.type, ast.Name)
                and handler.type.id in {'Exception', 'BaseException'}
            )
            if not is_broad:
                continue
            for child in ast.walk(handler):
                if not isinstance(child, ast.Raise) or not isinstance(child.exc, ast.Call):
                    continue
                expression = ast.get_source_segment(source, child.exc) or ''
                if 'HTTPException' in expression and ('400' in expression or 'HTTP_400' in expression):
                    offenders.append(f'{path.relative_to(backend_root)}:{handler.lineno}')
    assert offenders == []
