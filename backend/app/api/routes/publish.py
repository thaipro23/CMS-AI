from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.models.question import Question
from app.models.publish import PublishBatch, PublishBatchItem
from app.schemas.question import QuestionOut
from app.modules.publisher.service import OpenEdXPublisher
from app.services.audit_log import AuditErrorType, log_audit

router = APIRouter()


@router.post('/questions/{question_id}/openedx/dry-run')
async def dry_run_publish_question_to_openedx(question_id: str, mode: str = Query('publish_new'), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx'))):
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail='Question not found')
    ensure_course_access(user, question.course_id)
    try:
        result = await OpenEdXPublisher(db).dry_run_question(question_id, mode=mode)
        log_audit(db, action='openedx.publish_dry_run.question', status='success', message='Kiểm tra publish câu hỏi sang Open edX thành công', user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'target_library_key': question.target_library_key, 'difficulty': question.difficulty, 'result': result, 'mode': mode})
        return result
    except ValueError as exc:
        log_audit(db, action='openedx.publish_dry_run.question', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/questions/{question_id}/openedx', response_model=QuestionOut)
async def publish_question_to_openedx(question_id: str, mode: str = Query('publish_new'), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx')), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail='Question not found')
    ensure_course_access(user, question.course_id)
    idempotency_key = (idempotency_key or '').strip() or None
    single_batch = None
    if idempotency_key:
        batch_mode = f'question_{mode}'[:50]
        existing = db.query(PublishBatch).filter(
            PublishBatch.course_id == question.course_id,
            PublishBatch.actor_id == user.user_id,
            PublishBatch.mode == batch_mode,
            PublishBatch.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return question
        single_batch = PublishBatch(course_id=question.course_id, actor_id=user.user_id, mode=batch_mode, total_questions=1, status='running', idempotency_key=idempotency_key)
        db.add(single_batch)
        db.commit()
        db.refresh(single_batch)
    try:
        published = await OpenEdXPublisher(db).publish_question(question_id, actor=user.user_id, mode=mode, batch_id=single_batch.id if single_batch else None)
        if single_batch:
            single_batch.status = 'success' if published.openedx_verification_status == 'verified' else 'warning'
            single_batch.published_count = 1
            single_batch.warning_count = 0 if published.openedx_verification_status == 'verified' else 1
            items = db.query(PublishBatchItem).filter(PublishBatchItem.batch_id == single_batch.id).all()
            single_batch.summary_json = {'question_id': question_id, 'publish_status': published.publish_status, 'item_count': len(items)}
            db.commit()
        audit_status = 'success' if published.openedx_verification_status == 'verified' else 'warning'
        log_audit(db, action='openedx.publish.question', status=audit_status, message='Publish câu hỏi sang Open edX hoàn tất' if audit_status == 'success' else 'Đã import nhưng cần verify/manual publish trong Open edX', user=user, course_id=published.course_id, target_type='question', target_id=question_id, metadata={'target_library_key': published.target_library_key, 'difficulty': published.difficulty, 'source_node_id': published.source_node_id, 'publish_status': published.publish_status, 'mode': mode})
        return published
    except ValueError as exc:
        if 'single_batch' in locals() and single_batch:
            single_batch.status = 'failed'; single_batch.failed_count = 1; single_batch.errors_json = [{'question_id': question_id, 'error': str(exc)}]; db.commit()
        log_audit(db, action='openedx.publish.question', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if 'single_batch' in locals() and single_batch:
            single_batch.status = 'failed'; single_batch.failed_count = 1; single_batch.errors_json = [{'question_id': question_id, 'error': str(exc)}]; db.commit()
        log_audit(db, action='openedx.publish.question', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'target_library_key': question.target_library_key})
        raise HTTPException(status_code=502, detail=f'Open edX publish failed: {exc}') from exc


@router.post('/courses/{course_id}/openedx/dry-run')
async def dry_run_publish_course_to_openedx(course_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx'))):
    ensure_course_access(user, course_id)
    result = await OpenEdXPublisher(db).dry_run_course_approved(course_id)
    log_audit(db, action='openedx.publish_dry_run.course', status='success', message='Kiểm tra publish toàn bộ course sang Open edX thành công', user=user, course_id=course_id, target_type='course', target_id=course_id, metadata={'result': result})
    return result


@router.post('/courses/{course_id}/openedx')
async def publish_course_to_openedx(course_id: str, mode: str = Query('publish_new'), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx')), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    ensure_course_access(user, course_id)
    try:
        result = await OpenEdXPublisher(db).publish_course_approved(course_id, actor=user.user_id, mode=mode, idempotency_key=idempotency_key)
        if result.get('failed'):
            status = 'partial_success' if result.get('published') else 'failed'
            log_audit(db, action='openedx.publish.course', status=status, error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR if not result.get('published') else None, message='Publish sang Open edX có lỗi, xem errors để biết chi tiết', user=user, course_id=course_id, target_type='course', target_id=course_id, metadata={'result': result})
            if not result.get('published'):
                first_error = (result.get('errors') or [{}])[0].get('error') or 'Không publish được câu nào sang Open edX.'
                raise HTTPException(status_code=502, detail=first_error)
            return result
        audit_status = 'warning' if result.get('warnings') else 'success'
        log_audit(db, action='openedx.publish.course', status=audit_status, message='Publish toàn bộ câu approved sang Open edX thành công' if audit_status == 'success' else 'Publish xong nhưng còn pending/manual verify trong Open edX', user=user, course_id=course_id, target_type='course', target_id=course_id, metadata={'result': result})
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        log_audit(db, action='openedx.publish.course', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=course_id, target_type='course', target_id=course_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_audit(db, action='openedx.publish.course', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, course_id=course_id, target_type='course', target_id=course_id)
        raise HTTPException(status_code=502, detail=f'Open edX publish failed: {exc}') from exc


@router.get('/courses/{course_id}/openedx/history')
def publish_course_history(course_id: str, limit: int = 20, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx'))):
    ensure_course_access(user, course_id)
    return OpenEdXPublisher(db).publish_history(course_id, limit=limit)


@router.post('/batches/{batch_id}/rollback')
async def rollback_publish_batch(batch_id: str, level: str = Query('ai_server'), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_to_openedx')), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    batch = db.get(PublishBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail='Publish batch not found')
    ensure_course_access(user, batch.course_id)
    try:
        result = await OpenEdXPublisher(db).rollback_batch(batch_id, actor=user.user_id, level=level, idempotency_key=idempotency_key)
        log_audit(db, action='openedx.publish.rollback', status='success', message='Rollback batch publish thành công', user=user, course_id=batch.course_id, target_type='publish_batch', target_id=batch_id, metadata={'result': result, 'level': level})
        return result
    except Exception as exc:
        log_audit(db, action='openedx.publish.rollback', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, course_id=batch.course_id, target_type='publish_batch', target_id=batch_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
