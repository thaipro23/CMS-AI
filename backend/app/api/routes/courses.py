from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import hashlib
import uuid
from app.core.errors import public_http_exception
from app.db.session import get_db
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.models.course import ContentChunk, CourseSyncState, Topic
from app.schemas.course import (
    SyncCourseRequest,
    SyncCourseResponse,
    ContentChunkResponse,
    CourseFileUploadResponse,
    CourseNodeDeleteResponse,
    CourseCleanResyncResponse,
    CourseOptionResponse,
    TopicResponse,
    CourseTreeNodeResponse,
    CourseNodeOptionResponse,
)
from app.services.openedx_client import OpenEdxClient
from app.services.course_sync import CourseSyncService
from app.algorithms.course_tree import CourseTreeBuilder, CourseTreeNode
from app.services.audit_log import log_audit
from app.services.chunker import Chunker
from app.services.content_extractor import ContentExtractor
from app.services.token_counter import count_tokens

router = APIRouter()


_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
_UPLOAD_ALLOWED_EXTENSIONS = {
    'pdf', 'pptx', 'ppt', 'docx', 'xlsx', 'xlsm', 'csv', 'tsv',
    'txt', 'md', 'markdown', 'html', 'htm', 'json', 'xml', 'srt', 'vtt'
}
_LEGACY_OFFICE_EXTENSIONS = {'doc', 'xls'}
_LOCAL_NODE_TYPES = {'uploaded_file', 'manual_file', 'ai_uploaded_file'}
_DELETE_CONFIRM_TEXT = 'DELETE_NODE'
_CLEAN_RESYNC_CONFIRM_TEXT = 'RESET_COURSE_SYNC'


def _safe_upload_filename(filename: str) -> str:
    name = (filename or 'uploaded-file').replace('\\', '/').rsplit('/', 1)[-1].strip()
    name = ''.join(ch if ch.isalnum() or ch in {' ', '.', '_', '-', '(', ')'} else '_' for ch in name)
    return name[:180] or 'uploaded-file'


def _upload_ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _upload_node_title(filename: str) -> str:
    return f'File bổ sung: {filename}'


def _upload_node_id(course_id: str, parent_node_id: str, filename: str, replace_existing: bool) -> str:
    base = f'{course_id}|{parent_node_id}|{filename}'
    if not replace_existing:
        base = f'{base}|{uuid.uuid4()}'
    digest = hashlib.sha256(base.encode('utf-8')).hexdigest()[:18]
    stem = filename.rsplit('.', 1)[0]
    slug = ''.join(ch.lower() if ch.isalnum() else '-' for ch in stem)[:60].strip('-') or 'file'
    return f'ai-upload:{digest}:{slug}'


def _is_deletable_local_node(state: CourseSyncState | None) -> bool:
    if state is None:
        return False
    block_id = state.block_id or ''
    block_type = (state.block_type or '').lower()
    return block_type in _LOCAL_NODE_TYPES or block_id.startswith('ai-upload:') or block_id.startswith('uploaded://')


def _state_descendant_ids(db: Session, course_id: str, node_id: str) -> set[str]:
    states = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()
    children: dict[str | None, list[str]] = {}
    for state in states:
        children.setdefault(state.parent_block_id, []).append(state.block_id)
    result: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result




async def _read_upload_limited(file: UploadFile, *, max_bytes: int = _UPLOAD_MAX_BYTES) -> bytes:
    """Read upload in chunks and reject oversize before buffering the full body.

    ContentExtractor currently needs bytes for PDF/PPTX/DOCX parsing, so the final
    accepted file still becomes bytes, but we never call await file.read() on an
    unbounded request. This prevents accidental 100MB+ requests from being loaded
    entirely into memory before validation.
    """
    content_length = None
    try:
        content_length = int(file.headers.get('content-length') or 0)
    except Exception:
        content_length = None
    if content_length and content_length > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='File quá lớn. Giới hạn hiện tại là 50MB/file.')

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='File quá lớn. Giới hạn hiện tại là 50MB/file.')
        chunks.append(chunk)
    return b''.join(chunks)

def _chunk_policy_for_uploaded_source(source_type: str) -> tuple[int, int]:
    source = (source_type or '').lower()
    if source in {'csv', 'tsv', 'xlsx', 'xlsm'}:
        return 1100, 80
    if source in {'pdf', 'pptx', 'ppt', 'docx'}:
        return 1000, 120
    if source in {'srt', 'vtt'}:
        return 900, 100
    return 1000, 100



@router.get('', response_model=list[CourseOptionResponse])
def list_synced_courses(
    search: str = Query(default='', description='Tìm theo mã khóa học đã từng sync/index trong AI Server'),
    limit: int = Query(default=1000, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    """Return courses already visible in AI Server local DB.

    This powers the /sync course picker. It intentionally lists only courses that
    AI Server has seen before through sync/chunks. New course IDs are still typed
    manually and synced via POST /courses/sync.
    """
    ensure_course_access(user, None)
    term = (search or '').strip()

    state_query = db.query(
        CourseSyncState.course_id.label('course_id'),
        func.count(CourseSyncState.id).label('node_count'),
        func.max(CourseSyncState.last_synced_at).label('last_synced_at'),
        func.min(CourseSyncState.created_at).label('first_created_at'),
    )
    if user.role != 'admin' and user.course_ids:
        state_query = state_query.filter(CourseSyncState.course_id.in_(user.course_ids))
    if term:
        state_query = state_query.filter(CourseSyncState.course_id.ilike(f'%{term}%'))
    state_rows = state_query.group_by(CourseSyncState.course_id).all()

    chunk_query = db.query(
        ContentChunk.course_id.label('course_id'),
        func.count(ContentChunk.id).label('chunk_count'),
        func.coalesce(func.sum(ContentChunk.token_count), 0).label('token_count'),
    )
    if user.role != 'admin' and user.course_ids:
        chunk_query = chunk_query.filter(ContentChunk.course_id.in_(user.course_ids))
    if term:
        chunk_query = chunk_query.filter(ContentChunk.course_id.ilike(f'%{term}%'))
    chunk_rows = {row.course_id: row for row in chunk_query.group_by(ContentChunk.course_id).all()}

    root_query = db.query(CourseSyncState.course_id, CourseSyncState.display_name).filter(CourseSyncState.parent_block_id.is_(None))
    if user.role != 'admin' and user.course_ids:
        root_query = root_query.filter(CourseSyncState.course_id.in_(user.course_ids))
    root_titles = {row.course_id: row.display_name for row in root_query.all()}

    by_course: dict[str, dict] = {}
    for row in state_rows:
        chunks = chunk_rows.get(row.course_id)
        by_course[row.course_id] = {
            'course_id': row.course_id,
            'title': root_titles.get(row.course_id) or row.course_id,
            'node_count': int(row.node_count or 0),
            'chunk_count': int(getattr(chunks, 'chunk_count', 0) or 0),
            'token_count': int(getattr(chunks, 'token_count', 0) or 0),
            'last_synced_at': row.last_synced_at or row.first_created_at,
        }

    for course_id, chunks in chunk_rows.items():
        if course_id not in by_course:
            by_course[course_id] = {
                'course_id': course_id,
                'title': root_titles.get(course_id) or course_id,
                'node_count': 0,
                'chunk_count': int(getattr(chunks, 'chunk_count', 0) or 0),
                'token_count': int(getattr(chunks, 'token_count', 0) or 0),
                'last_synced_at': None,
            }

    courses = sorted(
        by_course.values(),
        key=lambda item: (item.get('last_synced_at') is not None, item.get('last_synced_at') or datetime.min, item['course_id']),
        reverse=True,
    )
    return courses[:limit]


@router.post('/sync', response_model=SyncCourseResponse)
async def sync_course(payload: SyncCourseRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('sync_course'))):
    ensure_course_access(user, payload.course_id)
    client = OpenEdxClient()
    try:
        blocks = await client.get_course_blocks(payload.course_id)
        seen, changed = CourseSyncService(db).sync_blocks(payload.course_id, blocks, payload.force)
        log_audit(db, action='course.sync', status='success', message='Đồng bộ học liệu thành công', user=user, course_id=payload.course_id, target_type='course', metadata={'blocks_seen': seen, 'changed_blocks': changed, 'force': payload.force})
    except Exception as exc:
        log_audit(db, action='course.sync', status='failed', error_type='external', message='Không thể hoàn tất thao tác khóa học.', user=user, course_id=payload.course_id, target_type='course', metadata={'force': payload.force})
        raise
    return SyncCourseResponse(course_id=payload.course_id, blocks_seen=seen, changed_blocks=changed, status='completed')


@router.post('/{course_id}/clean-resync', response_model=CourseCleanResyncResponse)
async def clean_resync_course(
    course_id: str,
    confirm: str = Query(default='', description='Bắt buộc nhập RESET_COURSE_SYNC để xóa dữ liệu sync và đồng bộ lại'),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('sync_course')),
):
    """Delete local synced course-source data, then sync fresh data from CMS/Studio.

    This is intentionally limited to AI Server source-index data: course tree
    states, content chunks and deprecated topics. It does not delete the question
    bank, generated jobs, approved questions, or Open edX Studio content.
    """
    ensure_course_access(user, course_id)
    if confirm != _CLEAN_RESYNC_CONFIRM_TEXT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Thiếu xác nhận. Vui lòng nhập RESET_COURSE_SYNC để xóa dữ liệu đồng bộ cũ và đồng bộ lại.')

    try:
        deleted_chunks = db.query(ContentChunk).filter(ContentChunk.course_id == course_id).delete(synchronize_session=False)
        deleted_nodes = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).delete(synchronize_session=False)
        deleted_topics = db.query(Topic).filter(Topic.course_id == course_id).delete(synchronize_session=False)
        db.commit()

        client = OpenEdxClient()
        blocks = await client.get_course_blocks(course_id)
        seen, changed = CourseSyncService(db).sync_blocks(course_id, blocks, True)
        log_audit(
            db,
            action='course.clean_resync',
            status='success',
            message='Xóa dữ liệu học liệu cũ trong AI Server và đồng bộ lại từ CMS thành công',
            user=user,
            course_id=course_id,
            target_type='course',
            metadata={
                'deleted_chunks': deleted_chunks,
                'deleted_nodes': deleted_nodes,
                'deleted_topics': deleted_topics,
                'blocks_seen': seen,
                'changed_blocks': changed,
                'confirm': confirm,
            },
        )
    except Exception as exc:
        db.rollback()
        log_audit(db, action='course.clean_resync', status='failed', error_type='external', message='Không thể hoàn tất thao tác khóa học.', user=user, course_id=course_id, target_type='course', metadata={'confirm': confirm})
        raise

    return CourseCleanResyncResponse(
        course_id=course_id,
        deleted_chunks=deleted_chunks,
        deleted_nodes=deleted_nodes,
        deleted_topics=deleted_topics,
        blocks_seen=seen,
        changed_blocks=changed,
        status='completed',
        message='Đã xóa dữ liệu đồng bộ cũ trong AI Server và đồng bộ lại từ CMS/Studio.',
    )


def _states_to_blocks(states: list[CourseSyncState]) -> list[dict]:
    return [{
        'block_id': state.block_id,
        'parent_block_id': state.parent_block_id,
        'type': state.block_type,
        'display_name': state.display_name,
    } for state in states]


def _build_tree_with_stats(course_id: str, db: Session) -> list[CourseTreeNode]:
    states = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()
    roots = CourseTreeBuilder().build(_states_to_blocks(states))
    direct_stats: dict[str, dict[str, int]] = {}
    for chunk in db.query(ContentChunk).filter(ContentChunk.course_id == course_id).all():
        item = direct_stats.setdefault(chunk.block_id, {'chunk_count': 0, 'token_count': 0})
        item['chunk_count'] += 1
        item['token_count'] += chunk.token_count or 0

    def apply(node: CourseTreeNode) -> tuple[int, int]:
        direct = direct_stats.get(node.node_id, {'chunk_count': 0, 'token_count': 0})
        chunk_count = direct['chunk_count']
        token_count = direct['token_count']
        for child in node.children:
            child_chunks, child_tokens = apply(child)
            chunk_count += child_chunks
            token_count += child_tokens
        node.raw = node.raw | {'chunk_count': chunk_count, 'token_count': token_count}
        return chunk_count, token_count

    for root in roots:
        apply(root)
    return roots


def _descendant_block_ids(course_id: str, node_id: str, db: Session) -> set[str]:
    if not node_id or node_id == 'all':
        return set()
    roots = _build_tree_with_stats(course_id, db)
    builder = CourseTreeBuilder()
    all_nodes = builder.traverse(roots)
    target = next((node for node in all_nodes if node.node_id == node_id), None)
    if target is None:
        return {node_id}
    return {node.node_id for node in builder.traverse([target])}


def _node_path(node: CourseTreeNode, parent_path: str = '') -> str:
    current = node.title or node.node_id
    return f'{parent_path} / {current}' if parent_path else current


@router.post('/{course_id}/nodes/{node_id}/files', response_model=CourseFileUploadResponse)
async def upload_file_to_node(
    course_id: str,
    node_id: str,
    file: UploadFile = File(...),
    replace_existing: bool = Form(default=True),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('sync_course')),
):
    """Upload a teacher-provided file as a NEW child node under a CMS node.

    The file does not mutate Open edX.  AI Server creates a local child node
    (`uploaded_file`) below the selected CMS node, extracts text into chunks under
    that child node, and generation can select either the parent scope or the
    uploaded child node directly.  If replace_existing is true, re-uploading the
    same filename to the same parent refreshes that uploaded child node.
    """
    ensure_course_access(user, course_id)
    filename = _safe_upload_filename(file.filename or 'uploaded-file')
    ext = _upload_ext(filename)
    if ext in _LEGACY_OFFICE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'File .{ext} là định dạng Office cũ. Vui lòng chuyển sang .docx/.xlsx hoặc PDF trước khi upload để hệ thống tách nội dung ổn định.',
        )
    if ext not in _UPLOAD_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Định dạng .{ext or "unknown"} chưa được hỗ trợ. Hỗ trợ: {", ".join(sorted(_UPLOAD_ALLOWED_EXTENSIONS))}.',
        )

    parent_state = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == node_id).first()
    if parent_state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Không tìm thấy node cha. Hãy đồng bộ course trước rồi chọn đúng node trong cây nội dung.')

    upload_node_id = _upload_node_id(course_id, node_id, filename, replace_existing)
    upload_ref = f'uploaded://{upload_node_id}/{filename}'
    legacy_upload_ref = f'uploaded://{node_id}/{filename}'
    upload_title = _upload_node_title(filename)

    raw = await _read_upload_limited(file)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='File rỗng, không có nội dung để xử lý.')

    extractor = ContentExtractor()
    try:
        items = extractor.extract_asset({
            'asset_id': upload_ref,
            'url': upload_ref,
            'source_ref': upload_ref,
            'filename': filename,
            'display_name': filename,
            'mime_type': file.content_type or '',
            'bytes': raw,
            'strict': True,
        }, parent_block_id=upload_node_id)
    except ValueError as exc:
        raise public_http_exception(status_code=status.HTTP_400_BAD_REQUEST, code='COURSE_OPERATION_FAILED', message='Không thể hoàn tất thao tác khóa học.', logger_name=__name__) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Không đọc được file {filename}: {exc}')

    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'File {filename} không tách được text. Nếu là ảnh scan, cần OCR/transcript riêng trước khi đưa vào AI.')

    upload_state = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == upload_node_id).first()
    if upload_state is None:
        upload_state = CourseSyncState(
            course_id=course_id,
            block_id=upload_node_id,
            parent_block_id=node_id,
            block_type='uploaded_file',
            display_name=upload_title,
            sync_status='uploaded_child_node',
        )
        db.add(upload_state)
    upload_state.parent_block_id = node_id
    upload_state.block_type = 'uploaded_file'
    upload_state.display_name = upload_title
    upload_state.sync_status = 'uploaded_child_node'
    upload_state.last_synced_at = datetime.utcnow()

    if replace_existing:
        db.query(ContentChunk).filter(
            ContentChunk.course_id == course_id,
            ContentChunk.block_id == upload_node_id,
        ).delete(synchronize_session=False)
        # v25.9.12.9 migration guard: remove chunks created by v25.9.12.8,
        # which attached uploaded files directly to the selected CMS node instead
        # of creating a child node.
        db.query(ContentChunk).filter(
            ContentChunk.course_id == course_id,
            ContentChunk.block_id == node_id,
            ContentChunk.source_ref.like(f'{legacy_upload_ref}%'),
        ).delete(synchronize_session=False)

    chunker = Chunker()
    chunks_created = 0
    tokens_indexed = 0
    source_types: set[str] = set()

    for item in items:
        source_type = (item.source_type or ext or 'file').lower()
        source_types.add(source_type)
        max_tokens, overlap_tokens = _chunk_policy_for_uploaded_source(source_type)
        text_chunks = chunker.chunk_text(item.content, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        if not text_chunks and item.content.strip():
            text_chunks = [item.content]
        for index, chunk_text in enumerate(text_chunks, start=1):
            source_ref = item.source_ref or upload_ref
            if len(text_chunks) > 1:
                source_ref = f'{source_ref}#chunk={index}'
            token_count = count_tokens(chunk_text)
            db.add(ContentChunk(
                course_id=course_id,
                block_id=upload_node_id,
                content=chunk_text,
                token_count=token_count,
                source_type=source_type,
                page_number=item.page_number,
                timestamp_start=item.timestamp_start,
                timestamp_end=item.timestamp_end,
                source_ref=source_ref,
            ))
            chunks_created += 1
            tokens_indexed += token_count

    parent_state.sync_status = 'synced_with_uploaded_child_node'
    log_audit(
        db,
        action='course.node_file_upload',
        status='success',
        message='Tải file lên node và tách nội dung thành công',
        user=user,
        course_id=course_id,
        target_type='course_node',
        target_id=upload_node_id,
        metadata={'filename': filename, 'parent_node_id': node_id, 'created_node_id': upload_node_id, 'chunks_created': chunks_created, 'tokens_indexed': tokens_indexed, 'source_types': sorted(source_types)},
    )
    db.commit()
    return CourseFileUploadResponse(
        course_id=course_id,
        node_id=upload_node_id,
        parent_node_id=node_id,
        filename=filename,
        source_type=','.join(sorted(source_types)) or ext or 'file',
        chunks_created=chunks_created,
        tokens_indexed=tokens_indexed,
        status='completed',
        message='File đã được tạo thành node con mới và có thể dùng để tạo Learning Check.',
    )


@router.delete('/{course_id}/nodes/{node_id}', response_model=CourseNodeDeleteResponse)
def delete_course_node(
    course_id: str,
    node_id: str,
    confirm: str = Query(default='', description='Bắt buộc nhập DELETE_NODE để xác nhận xóa node'),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('sync_course')),
):
    ensure_course_access(user, course_id)
    if confirm != _DELETE_CONFIRM_TEXT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Thiếu xác nhận xóa node. Vui lòng nhập DELETE_NODE để xác nhận.')

    state = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == node_id).first()
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Không tìm thấy node cần xóa.')
    if not _is_deletable_local_node(state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Chỉ được xóa node con do AI Server tạo khi upload file. Node CMS/Open edX thật không bị xóa trong AI Server để tránh lệch dữ liệu; hãy xóa trong Studio nếu muốn xóa học liệu gốc.')

    node_ids = _state_descendant_ids(db, course_id, node_id)
    states = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id.in_(node_ids)).all()
    if any(not _is_deletable_local_node(item) for item in states):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Node này có chứa node CMS thật bên trong nên không thể xóa từ AI Server.')

    chunks_deleted = db.query(ContentChunk).filter(ContentChunk.course_id == course_id, ContentChunk.block_id.in_(node_ids)).delete(synchronize_session=False)
    states_deleted = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id.in_(node_ids)).delete(synchronize_session=False)
    log_audit(
        db,
        action='course.node_delete',
        status='success',
        message='Xóa node con upload khỏi AI Server thành công',
        user=user,
        course_id=course_id,
        target_type='course_node',
        target_id=node_id,
        metadata={'node_ids': sorted(node_ids), 'states_deleted': states_deleted, 'chunks_deleted': chunks_deleted},
    )
    db.commit()
    return CourseNodeDeleteResponse(course_id=course_id, node_id=node_id, deleted_nodes=states_deleted, deleted_chunks=chunks_deleted, status='deleted', message='Đã xóa node con và toàn bộ chunk liên quan khỏi AI Server.')


@router.get('/{course_id}/chunks', response_model=list[ContentChunkResponse], dependencies=[Depends(require_permission('view_questions'))])
def list_course_chunks(
    course_id: str,
    source_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
    topic_id: str | None = Query(default=None, description='Deprecated. Use node_id instead.'),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    ensure_course_access(user, course_id)
    query = db.query(ContentChunk).filter(ContentChunk.course_id == course_id)
    if source_type and source_type != 'all':
        query = query.filter(ContentChunk.source_type == source_type)
    # v20: filter by Open edX course node instead of inferred topic.
    selected_node_id = node_id if node_id and node_id != 'all' else None
    if selected_node_id:
        block_ids = _descendant_block_ids(course_id, selected_node_id, db)
        query = query.filter(ContentChunk.block_id.in_(block_ids))
    elif topic_id and topic_id != 'all':
        # Backward compatible only; new UI no longer sends topic_id.
        query = query.filter(ContentChunk.topic_id == topic_id)
    if search:
        like = f'%{search}%'
        query = query.filter((ContentChunk.content.ilike(like)) | (ContentChunk.block_id.ilike(like)) | (ContentChunk.source_ref.ilike(like)))
    chunks = query.order_by(ContentChunk.created_at.desc()).limit(limit).all()
    return chunks


@router.get('/{course_id}/chunks/page')
def list_course_chunks_page(
    course_id: str,
    source_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
    topic_id: str | None = Query(default=None, description='Deprecated. Use node_id instead.'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    """Paginated chunk endpoint for Workflow/Generate screens."""
    ensure_course_access(user, course_id)
    query = db.query(ContentChunk).filter(ContentChunk.course_id == course_id)
    if source_type and source_type != 'all':
        query = query.filter(ContentChunk.source_type == source_type)
    selected_node_id = node_id if node_id and node_id != 'all' else None
    if selected_node_id:
        block_ids = _descendant_block_ids(course_id, selected_node_id, db)
        query = query.filter(ContentChunk.block_id.in_(block_ids))
    elif topic_id and topic_id != 'all':
        query = query.filter(ContentChunk.topic_id == topic_id)
    if search:
        like = f'%{search}%'
        query = query.filter((ContentChunk.content.ilike(like)) | (ContentChunk.block_id.ilike(like)) | (ContentChunk.source_ref.ilike(like)))
    total = query.count()
    total_tokens = int(query.with_entities(func.coalesce(func.sum(ContentChunk.token_count), 0)).scalar() or 0)
    rows = query.order_by(ContentChunk.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'items': rows,
        'total': total,
        'total_tokens': total_tokens,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    }


@router.get('/{course_id}/tree', response_model=list[CourseTreeNodeResponse])
def course_tree(course_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    roots = _build_tree_with_stats(course_id, db)

    def to_response(node: CourseTreeNode, parent_path: str = ''):
        path = _node_path(node, parent_path)
        return CourseTreeNodeResponse(
            node_id=node.node_id,
            parent_id=node.parent_id,
            block_type=node.block_type,
            title=node.title,
            path=path,
            chunk_count=int(node.raw.get('chunk_count') or 0),
            token_count=int(node.raw.get('token_count') or 0),
            children=[to_response(child, path) for child in node.children],
        )
    return [to_response(root) for root in roots]


@router.get('/{course_id}/nodes', response_model=list[CourseNodeOptionResponse])
def course_nodes(course_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    roots = _build_tree_with_stats(course_id, db)
    rows: list[CourseNodeOptionResponse] = []

    def walk(node: CourseTreeNode, depth: int = 0, parent_path: str = ''):
        path = _node_path(node, parent_path)
        rows.append(CourseNodeOptionResponse(
            node_id=node.node_id,
            parent_id=node.parent_id,
            block_type=node.block_type,
            title=node.title,
            path=path,
            depth=depth,
            chunk_count=int(node.raw.get('chunk_count') or 0),
            token_count=int(node.raw.get('token_count') or 0),
        ))
        for child in node.children:
            walk(child, depth + 1, path)

    for root in roots:
        walk(root)
    return rows


@router.get('/{course_id}/topics', response_model=list[TopicResponse])
def list_topics(course_id: str, refresh: bool = Query(default=False), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    """Deprecated in v20.

    Topic extraction was removed from the main UX because it produced confusing
    labels for real Vietnamese/Open edX courses. Use /courses/{course_id}/nodes
    and /courses/{course_id}/tree instead.
    """
    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.importance_score.desc()).limit(300).all()
    topic_stats = {
        row.topic_id: row
        for row in db.query(
            ContentChunk.topic_id.label('topic_id'),
            func.count(ContentChunk.id).label('chunk_count'),
            func.coalesce(func.sum(ContentChunk.token_count), 0).label('token_count'),
        )
        .filter(ContentChunk.course_id == course_id, ContentChunk.topic_id.isnot(None))
        .group_by(ContentChunk.topic_id)
        .all()
    }
    counts = {topic_id: int(getattr(row, 'chunk_count', 0) or 0) for topic_id, row in topic_stats.items()}
    token_counts = {topic_id: int(getattr(row, 'token_count', 0) or 0) for topic_id, row in topic_stats.items()}
    return [TopicResponse(
        id=t.id,
        course_id=t.course_id,
        lesson_id=t.lesson_id,
        title=t.title,
        summary=t.summary,
        importance_score=t.importance_score,
        chunk_count=counts.get(t.id, 0),
        token_count=token_counts.get(t.id, 0),
    ) for t in topics]
