from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, require_permission
from app.schemas.settings import RuntimeSettingsUpdate
from app.services.model_gateway import ModelGateway
from app.services.runtime_settings import public_runtime_settings, update_runtime_settings, apply_runtime_settings
from app.services.openedx_verification import test_openedx_connection
from app.db.session import get_db
from app.services.audit_log import log_audit

router = APIRouter()


@router.get('/runtime')
def get_runtime_settings(_: UserContext = Depends(require_permission('manage_settings'))):
    """Admin-only runtime config.

    Secrets are masked on read but are environment-only. PATCH accepts only
    non-secret runtime knobs and rejects non-empty secret values.
    """
    return public_runtime_settings()


@router.patch('/runtime')
def patch_runtime_settings(
    payload: RuntimeSettingsUpdate,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    try:
        data = update_runtime_settings(payload.model_dump())
        log_audit(db, action='settings.update', status='success', message='Admin đã cập nhật cấu hình hệ thống', user=user, target_type='runtime_settings', metadata={'model': payload.model.openai_model if payload.model else None, 'mock_llm': payload.model.mock_llm if payload.model else None, 'auth_mode': payload.sso.auth_mode if payload.sso else None})
        return data
    except ValueError as exc:
        log_audit(db, action='settings.update', status='failed', error_type='user', message=str(exc), user=user, target_type='runtime_settings')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post('/runtime/test-model')
async def test_model_gateway(user: UserContext = Depends(require_permission('manage_settings')), db: Session = Depends(get_db)):
    """Admin-only smoke test for real GPT/local model settings.

    This endpoint runs in the backend container, reloads the same shared runtime
    config file used by the worker, and makes a 1-question call. It is intended
    to quickly verify whether MOCK_LLM=false + API key/model are actually active.
    """
    try:
        apply_runtime_settings()
        questions, usage = await ModelGateway().generate_questions(
            content='Nội dung kiểm thử: REST API dùng HTTP methods GET, POST, PUT, DELETE để thao tác tài nguyên.',
            question_count=1,
            scope_title='Settings smoke test',
            provider='openai',
        )
        log_audit(db, action='settings.test_model', status='success', message='Kiểm tra GPT thành công', user=user, target_type='model_gateway', metadata={'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'), 'model': usage.get('model')})
        return {
            'ok': True,
            'provider': usage.get('provider'),
            'model': usage.get('model'),
            'api_mode': usage.get('api_mode'),
            'input_tokens': usage.get('input_tokens'),
            'cached_input_tokens': usage.get('cached_input_tokens', 0),
            'output_tokens': usage.get('output_tokens'),
            'question_count': len(questions),
            'first_question': (questions[0].get('question') or questions[0].get('question_text')) if questions else None,
        }
    except Exception as exc:
        log_audit(db, action='settings.test_model', status='failed', error_type='external', message=str(exc), user=user, target_type='model_gateway')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post('/openedx/test')
async def test_openedx_settings(course_id: str | None = None, user: UserContext = Depends(require_permission('manage_settings')), db: Session = Depends(get_db)):
    """Admin-only Open edX connector smoke test."""
    apply_runtime_settings()
    try:
        result = await test_openedx_connection(course_id)
        log_audit(db, action='settings.test_openedx', status='success' if result.get('ok', True) else 'failed', error_type=None if result.get('ok', True) else 'external', message=result.get('message') or 'Đã kiểm tra Open edX', user=user, course_id=course_id, target_type='openedx_connector', metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='settings.test_openedx', status='failed', error_type='external', message=str(exc), user=user, course_id=course_id, target_type='openedx_connector')
        raise
