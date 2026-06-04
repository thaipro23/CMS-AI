from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.models.course import ContentChunk, CourseSyncState
from app.schemas.concept import ConceptExtractRequest, ConceptExtractResponse, ConceptListResponse
from app.services.audit_log import log_audit
from app.services.concept_service import ConceptService
from app.services.generation_planner import descendant_block_ids

router = APIRouter()


def _chunks_for_node(db: Session, course_id: str, node_id: str | None) -> list[ContentChunk]:
    query = db.query(ContentChunk).filter(ContentChunk.course_id == course_id)
    if node_id and node_id != 'all':
        block_ids = descendant_block_ids(course_id, node_id, db)
        query = query.filter(ContentChunk.block_id.in_(block_ids))
    return query.order_by(ContentChunk.created_at.asc()).all()


def _node_title(db: Session, course_id: str, node_id: str | None) -> str | None:
    if not node_id or node_id == 'all':
        return 'Toàn khóa học'
    state = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == node_id).first()
    return state.display_name if state else node_id


@router.get('/courses/{course_id}/concepts', response_model=ConceptListResponse)
def list_course_concepts(
    course_id: str,
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    ensure_course_access(user, course_id)
    concepts = ConceptService(db).list_concepts(course_id, node_id)
    return ConceptListResponse(course_id=course_id, node_id=node_id, total=len(concepts), concepts=concepts)


@router.post('/courses/{course_id}/concepts/extract', response_model=ConceptExtractResponse)
def extract_course_concepts(
    course_id: str,
    payload: ConceptExtractRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('generate_questions')),
):
    ensure_course_access(user, course_id)
    chunks = _chunks_for_node(db, course_id, payload.node_id)
    if not chunks:
        raise HTTPException(status_code=400, detail='Không có chunk học liệu để trích xuất concept. Hãy đồng bộ khóa học hoặc chọn node có nội dung trước.')
    service = ConceptService(db)
    concepts, reused = service.extract_for_chunks(
        course_id=course_id,
        chunks=chunks,
        node_id=payload.node_id if payload.node_id != 'all' else None,
        node_title=_node_title(db, course_id, payload.node_id),
        max_concepts=payload.max_concepts,
        force=payload.force,
    )
    log_audit(
        db,
        action='concept.extract',
        status='success',
        message='Đã trích xuất concept/vấn đề học tập từ học liệu',
        user=user,
        course_id=course_id,
        target_type='course_node',
        target_id=payload.node_id,
        metadata={'concept_count': len(concepts), 'force': payload.force, 'reused_existing': reused},
    )
    return ConceptExtractResponse(course_id=course_id, node_id=payload.node_id, concept_count=len(concepts), reused_existing=reused, concepts=concepts)
