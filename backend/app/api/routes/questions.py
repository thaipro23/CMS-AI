from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.rbac import UserContext, ensure_course_access, require_permission, restrict_query_to_courses
from app.models.question import Question
from app.models.course import ContentChunk, CourseSyncState
from app.services.source_chunk_refs import first_existing_content_chunk, get_existing_content_chunks, split_source_chunk_ids
from app.schemas.question import (
    BulkApproveRequest,
    ChangeQuestionStatusRequest,
    DraftErrorRepairRequest,
    KeepDraftErrorRequest,
    OpenEdxExportOut,
    QuestionBankStatsOut,
    QuestionOut,
    QuestionUpdateRequest,
    ReviewQuestionRequest,
)
from app.services.openedx_exporter import question_to_openedx_olx, questions_to_openedx_olx_package
from app.services.question_service import QuestionService
from app.services.audit_log import AuditErrorType, log_audit

router = APIRouter()

SORT_FIELDS = {
    'draft_error_reason': Question.draft_error_reason,
    'created_at': Question.created_at,
    'updated_at': Question.updated_at,
    'topic': Question.topic,
    'difficulty': Question.difficulty,
    'status': Question.status,
    'quality_score': Question.quality_score,
    'version': Question.version,
    'source_node_id': Question.source_node_id,
    'chapter_title': Question.chapter_title,
    'target_library_key': Question.target_library_key,
}


def _question_for_user(db: Session, question_id: str, user: UserContext) -> Question:
    try:
        question = QuestionService(db).get_or_raise(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ensure_course_access(user, question.course_id)
    return question


@router.get('', response_model=list[QuestionOut])
def list_questions(
    course_id: str | None = None,
    status: str | None = None,
    difficulty: str | None = None,
    topic: str | None = None,
    source_type: str | None = None,
    node_id: str | None = None,
    source_node_id: str | None = None,
    chapter_node_id: str | None = None,
    target_library_key: str | None = None,
    draft_error_reason: str | None = None,
    search: str | None = None,
    sort_by: str = 'created_at',
    sort_dir: str = 'desc',
    limit: int = 300,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    ensure_course_access(user, course_id)
    query = restrict_query_to_courses(db.query(Question), Question, user)
    if course_id:
        query = query.filter(Question.course_id == course_id)
    if status and status != 'all':
        query = query.filter(Question.status == status)
    if difficulty and difficulty != 'all':
        query = query.filter(Question.difficulty == difficulty)
    if source_type and source_type != 'all':
        query = query.filter(Question.source_type == source_type)
    if topic:
        query = query.filter(Question.topic.ilike(f'%{topic}%'))
    effective_node_id = source_node_id or node_id
    if effective_node_id and effective_node_id != 'all':
        query = query.filter(Question.source_node_id == effective_node_id)
    if chapter_node_id and chapter_node_id != 'all':
        query = query.filter(Question.chapter_node_id == chapter_node_id)
    if target_library_key:
        query = query.filter(Question.target_library_key == target_library_key)
    if draft_error_reason and draft_error_reason != 'all':
        query = query.filter(Question.draft_error_reason == draft_error_reason)
    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            Question.question_text.ilike(pattern),
            Question.explanation.ilike(pattern),
            Question.topic.ilike(pattern),
            Question.learning_objective.ilike(pattern),
            Question.source_ref.ilike(pattern),
            Question.source_excerpt.ilike(pattern),
            Question.source_node_id.ilike(pattern),
            Question.chapter_title.ilike(pattern),
            Question.target_library_key.ilike(pattern),
        ))
    sort_col = SORT_FIELDS.get(sort_by, Question.created_at)
    query = query.order_by(asc(sort_col) if sort_dir == 'asc' else desc(sort_col))
    return query.limit(min(max(limit, 1), 1000)).all()


@router.get('/page')
def list_questions_page(
    course_id: str | None = None,
    status: str | None = None,
    difficulty: str | None = None,
    topic: str | None = None,
    source_type: str | None = None,
    node_id: str | None = None,
    source_node_id: str | None = None,
    chapter_node_id: str | None = None,
    target_library_key: str | None = None,
    draft_error_reason: str | None = None,
    search: str | None = None,
    sort_by: str = 'created_at',
    sort_dir: str = 'desc',
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    """Paginated question bank endpoint for UI pagination.

    Selection is kept on the frontend by question id; this endpoint only changes
    which rows are visible on the current page.
    """
    ensure_course_access(user, course_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = restrict_query_to_courses(db.query(Question), Question, user)
    if course_id:
        query = query.filter(Question.course_id == course_id)
    if status and status != 'all':
        query = query.filter(Question.status == status)
    if difficulty and difficulty != 'all':
        query = query.filter(Question.difficulty == difficulty)
    if source_type and source_type != 'all':
        query = query.filter(Question.source_type == source_type)
    if topic:
        query = query.filter(Question.topic.ilike(f'%{topic}%'))
    effective_node_id = source_node_id or node_id
    if effective_node_id and effective_node_id != 'all':
        query = query.filter(Question.source_node_id == effective_node_id)
    if chapter_node_id and chapter_node_id != 'all':
        query = query.filter(Question.chapter_node_id == chapter_node_id)
    if target_library_key:
        query = query.filter(Question.target_library_key == target_library_key)
    if draft_error_reason and draft_error_reason != 'all':
        query = query.filter(Question.draft_error_reason == draft_error_reason)
    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            Question.question_text.ilike(pattern),
            Question.explanation.ilike(pattern),
            Question.topic.ilike(pattern),
            Question.learning_objective.ilike(pattern),
            Question.source_ref.ilike(pattern),
            Question.source_excerpt.ilike(pattern),
            Question.source_node_id.ilike(pattern),
            Question.chapter_title.ilike(pattern),
            Question.target_library_key.ilike(pattern),
        ))
    total = query.count()
    sort_col = SORT_FIELDS.get(sort_by, Question.created_at)
    rows = query.order_by(asc(sort_col) if sort_dir == 'asc' else desc(sort_col)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'items': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    }


@router.get('/stats', response_model=QuestionBankStatsOut)
def question_stats(course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    query = restrict_query_to_courses(db.query(Question), Question, user)
    if course_id:
        query = query.filter(Question.course_id == course_id)
    rows = query.all()
    counts = {s: 0 for s in ['pending_review', 'approved', 'rejected', 'published', 'draft_error']}
    for q in rows:
        if q.status in counts:
            counts[q.status] += 1
    return QuestionBankStatsOut(total=len(rows), **counts)


@router.get('/export/openedx-olx', response_model=OpenEdxExportOut)
def export_course_questions_olx(course_id: str, status: str = 'approved', db: Session = Depends(get_db), user: UserContext = Depends(require_permission('export_questions'))):
    ensure_course_access(user, course_id)
    questions = db.query(Question).filter(Question.course_id == course_id, Question.status == status).order_by(Question.topic.asc()).all()
    return OpenEdxExportOut(format='openedx_olx_problem_xml', question_count=len(questions), olx=questions_to_openedx_olx_package(questions))


@router.get('/export/openedx-olx.xml')
def download_course_questions_olx(course_id: str, status: str = 'approved', db: Session = Depends(get_db), user: UserContext = Depends(require_permission('export_questions'))):
    ensure_course_access(user, course_id)
    questions = db.query(Question).filter(Question.course_id == course_id, Question.status == status).order_by(Question.topic.asc()).all()
    xml = questions_to_openedx_olx_package(questions)
    return Response(content=xml, media_type='application/xml', headers={'Content-Disposition': f'attachment; filename="openedx_questions_{status}.xml"'})


@router.post('/bulk/approve')
def bulk_approve(payload: BulkApproveRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    ensure_course_access(user, payload.course_id)
    try:
        result = QuestionService(db).bulk_approve(
            actor=user.user_id,
            note=payload.note,
            question_ids=payload.question_ids,
            course_id=payload.course_id,
            approve_all_pending=payload.approve_all_pending,
            user=user,
        )
        log_audit(
            db,
            action='question.bulk_approve',
            status='success',
            message='Duyệt hàng loạt câu hỏi thành công',
            user=user,
            course_id=payload.course_id,
            target_type='question',
            metadata={
                'approve_all_pending': payload.approve_all_pending,
                'requested_ids': payload.question_ids or [],
                'approved_count': result.get('approved_count'),
                'skipped': result.get('skipped'),
            },
        )
        return result
    except ValueError as exc:
        log_audit(db, action='question.bulk_approve', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=payload.course_id, target_type='question')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/diversity/report')
def question_diversity_report(course_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    return QuestionService(db).diversity_report(course_id=course_id)


@router.get('/draft-errors/reasons')
def draft_error_reasons(course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    query = restrict_query_to_courses(db.query(Question), Question, user).filter(Question.status == 'draft_error')
    if course_id:
        query = query.filter(Question.course_id == course_id)
    rows = query.all()
    counts: dict[str, int] = {}
    for q in rows:
        key = q.draft_error_reason or 'unknown'
        counts[key] = counts.get(key, 0) + 1
    return {'total': len(rows), 'by_reason': counts}


@router.get('/{question_id}/source-trace')
def get_question_source_trace(question_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    question = _question_for_user(db, question_id, user)
    source_chunk_ids = split_source_chunk_ids(question.source_chunk_id)
    chunks = get_existing_content_chunks(db, source_chunk_ids) if source_chunk_ids else []
    chunk = chunks[0] if chunks else None
    node = None
    chapter = None
    if question.source_node_id:
        node = db.query(CourseSyncState).filter(CourseSyncState.course_id == question.course_id, CourseSyncState.block_id == question.source_node_id).first()
    if question.chapter_node_id:
        chapter = db.query(CourseSyncState).filter(CourseSyncState.course_id == question.course_id, CourseSyncState.block_id == question.chapter_node_id).first()
    return {
        'question_id': question.id,
        'course_id': question.course_id,
        'source_node': {
            'id': question.source_node_id,
            'title': question.source_node_title or (node.display_name if node else None),
            'block_type': node.block_type if node else None,
            'sync_status': node.sync_status if node else None,
        },
        'chapter_node': {
            'id': question.chapter_node_id,
            'title': question.chapter_title or (chapter.display_name if chapter else None),
            'block_type': chapter.block_type if chapter else None,
        },
        'chunk': {
            'id': chunk.id if chunk else question.source_chunk_id,
            'block_id': chunk.block_id if chunk else question.block_id,
            'source_type': chunk.source_type if chunk else question.source_type,
            'source_ref': chunk.source_ref if chunk else question.source_ref,
            'page_number': chunk.page_number if chunk else question.source_page,
            'timestamp_start': chunk.timestamp_start if chunk else question.source_timestamp_start,
            'timestamp_end': chunk.timestamp_end if chunk else question.source_timestamp_end,
            'token_count': chunk.token_count if chunk else None,
            'content': (chunk.content if chunk else question.source_excerpt) or '',
        },
        'chunks': [
            {
                'id': c.id,
                'block_id': c.block_id,
                'source_type': c.source_type,
                'source_ref': c.source_ref,
                'page_number': c.page_number,
                'timestamp_start': c.timestamp_start,
                'timestamp_end': c.timestamp_end,
                'token_count': c.token_count,
                'content': c.content or '',
            }
            for c in chunks
        ],
        'source_chunk_ids': source_chunk_ids,
        'question_source_excerpt': question.source_excerpt,
        'concept': {
            'id': question.concept_id,
            'title': question.concept_title,
            'key': question.concept_key,
            'family_id': question.question_family_id,
            'variant_no': question.variant_no,
            'source_evidence': question.source_evidence,
        },
        'publish_trace': question.publish_verification_json or {},
        'tags': question.tags or [],
    }


@router.get('/{question_id}', response_model=QuestionOut)
def get_question(question_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return _question_for_user(db, question_id, user)


@router.get('/{question_id}/openedx-olx', response_model=OpenEdxExportOut)
def get_question_openedx_olx(question_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('export_questions'))):
    question = _question_for_user(db, question_id, user)
    return OpenEdxExportOut(format='openedx_olx_problem_xml', question_count=1, olx=question_to_openedx_olx(question))


@router.patch('/{question_id}', response_model=QuestionOut)
def update_question(question_id: str, payload: QuestionUpdateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    try:
        updated = QuestionService(db).update_question(question_id, payload, actor=user.user_id)
        log_audit(db, action='question.update', status='success', message='Cập nhật câu hỏi thành công', user=user, course_id=updated.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': updated.status})
        return updated
    except ValueError as exc:
        log_audit(db, action='question.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/{question_id}')
def delete_question(question_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('delete_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    course_id = question.course_id
    difficulty = question.difficulty
    source_node_id = question.source_node_id
    try:
        result = QuestionService(db).delete_question(question_id, actor=user.user_id)
        log_audit(db, action='question.delete', status='success', message='Xóa câu hỏi chưa publish thành công', user=user, course_id=course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'difficulty': difficulty, 'source_node_id': source_node_id})
        return result
    except ValueError as exc:
        log_audit(db, action='question.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/repair', response_model=QuestionOut)
def repair_draft_error(question_id: str, payload: DraftErrorRepairRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    old_draft_error_reason = question.draft_error_reason
    try:
        repaired = QuestionService(db).repair_draft_error(question_id, user.user_id, payload.note)
        log_audit(db, action='question.repair', status='success', message='Repair draft_error thành công', user=user, course_id=repaired.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': repaired.status, 'draft_error_reason': old_draft_error_reason, 'repair_attempt_count': repaired.repair_attempt_count})
        return repaired
    except ValueError as exc:
        log_audit(db, action='question.repair', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/keep-anyway', response_model=QuestionOut)
def keep_draft_error_anyway(question_id: str, payload: KeepDraftErrorRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    old_draft_error_reason = question.draft_error_reason
    try:
        kept = QuestionService(db).keep_draft_error_anyway(question_id, user.user_id, payload.note)
        log_audit(db, action='question.keep_anyway', status='success', message='Giữ câu draft_error theo quyết định của giáo viên', user=user, course_id=kept.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': kept.status, 'draft_error_reason': old_draft_error_reason, 'note': payload.note})
        return kept
    except ValueError as exc:
        log_audit(db, action='question.keep_anyway', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/status', response_model=QuestionOut)
def change_status(question_id: str, payload: ChangeQuestionStatusRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    try:
        changed = QuestionService(db).change_status(question_id, payload.target_status, user.user_id, payload.note)
        log_audit(db, action='question.status_change', status='success', message='Đổi trạng thái câu hỏi thành công', user=user, course_id=changed.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': changed.status, 'note': payload.note})
        return changed
    except ValueError as exc:
        log_audit(db, action='question.status_change', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'target_status': payload.target_status})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/approve', response_model=QuestionOut)
def approve_question(question_id: str, payload: ReviewQuestionRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    try:
        approved = QuestionService(db).transition(question_id, 'approved', user.user_id, payload.note)
        log_audit(db, action='question.approve', status='success', message='Duyệt câu hỏi thành công', user=user, course_id=approved.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': approved.status, 'difficulty': approved.difficulty})
        return approved
    except ValueError as exc:
        log_audit(db, action='question.approve', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/reject', response_model=QuestionOut)
def reject_question(question_id: str, payload: ReviewQuestionRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    try:
        rejected = QuestionService(db).transition(question_id, 'rejected', user.user_id, payload.note)
        log_audit(db, action='question.reject', status='success', message='Từ chối câu hỏi thành công', user=user, course_id=rejected.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': rejected.status, 'difficulty': rejected.difficulty})
        return rejected
    except ValueError as exc:
        log_audit(db, action='question.reject', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{question_id}/publish', response_model=QuestionOut)
def publish_question(question_id: str, payload: ReviewQuestionRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    question = _question_for_user(db, question_id, user)
    old_status = question.status
    try:
        published = QuestionService(db).transition(question_id, 'published', user.user_id, payload.note)
        log_audit(db, action='question.publish_local', status='success', message='Đánh dấu câu hỏi đã publish trong AI Server', user=user, course_id=published.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status, 'new_status': published.status, 'target_library_key': published.target_library_key})
        return published
    except ValueError as exc:
        log_audit(db, action='question.publish_local', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=question.course_id, target_type='question', target_id=question_id, metadata={'old_status': old_status})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
