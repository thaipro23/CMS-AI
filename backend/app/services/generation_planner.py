from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.algorithms.course_tree import CourseTreeBuilder, CourseTreeNode
from app.algorithms.largest_remainder import allocate_by_largest_remainder, allocation_as_dicts
from app.algorithms.node_coverage import NodeCoverageAllocator, content_signal, create_batches
from app.models.course import ContentChunk, CourseSyncState
from app.schemas.generation import GenerateQuestionsRequest
from app.services.token_counter import count_tokens
from app.services.generation_cache import build_generation_cache_key, build_prompt_cache_key, sha256_text
from app.services.concept_service import ConceptService, format_concepts_for_prompt

# v25.2: old v25.0 capped every call to 6 questions. That fixed parsing but
# repeated the same prompt/content too much. New default groups by difficulty:
# 20 questions with 50/30/20 becomes 10 EASY + 6 MEDIUM + 4 HARD = 3 calls.
DEFAULT_MAX_QUESTIONS_PER_MODEL_CALL = 12


@dataclass
class GenerationPlan:
    content: str
    content_tokens: int
    chunks: list[ContentChunk]
    node_allocations: list[dict]
    difficulty_allocations: list[dict]
    planned_batches: list[int]
    # Each work item is one real model call. Each item carries its own content
    # and target difficulty so Estimate and Worker do not resend unrelated nodes.
    work_items: list[dict]


def _states_to_blocks(states: list[CourseSyncState]) -> list[dict]:
    return [{
        'block_id': state.block_id,
        'parent_block_id': state.parent_block_id,
        'type': state.block_type,
        'display_name': state.display_name,
    } for state in states]


def _build_course_nodes(course_id: str, db: Session) -> list[CourseTreeNode]:
    states = db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()
    return CourseTreeBuilder().build(_states_to_blocks(states))


def descendant_block_ids(course_id: str, node_id: str, db: Session) -> set[str]:
    builder = CourseTreeBuilder()
    roots = _build_course_nodes(course_id, db)
    all_nodes = builder.traverse(roots)
    target = next((node for node in all_nodes if node.node_id == node_id), None)
    if target is None:
        return {node_id}
    return {node.node_id for node in builder.traverse([target])}


def node_title_map(course_id: str, db: Session) -> dict[str, dict]:
    roots = _build_course_nodes(course_id, db)
    rows: dict[str, dict] = {}

    def walk(node: CourseTreeNode, depth: int = 0, parent_path: str = ''):
        path = f'{parent_path} / {node.title}' if parent_path else node.title
        rows[node.node_id] = {'node_id': node.node_id, 'title': node.title, 'path': path, 'block_type': node.block_type, 'depth': depth}
        for child in node.children:
            walk(child, depth + 1, path)

    for root in roots:
        walk(root)
    return rows


def _explicit_problem_node_ids(db: Session, course_id: str, node_ids: list[str] | None) -> set[str]:
    selected = {node_id for node_id in (node_ids or []) if node_id and node_id != 'all'}
    if not selected:
        return set()
    states = db.query(CourseSyncState).filter(
        CourseSyncState.course_id == course_id,
        CourseSyncState.block_id.in_(selected),
    ).all()
    return {state.block_id for state in states if (state.block_type or '').lower() == 'problem'}


def query_chunks(db: Session, course_id: str, *, chunk_ids: list[str] | None = None, node_ids: list[str] | None = None) -> list[ContentChunk]:
    query = db.query(ContentChunk).filter(ContentChunk.course_id == course_id)
    if chunk_ids:
        # Explicit chunk selection is a teacher action, so selected problem chunks
        # are allowed and can be used as source context.
        return query.filter(ContentChunk.id.in_(chunk_ids)).order_by(ContentChunk.created_at.asc()).all()

    if node_ids:
        block_ids: set[str] = set()
        for node_id in node_ids:
            if node_id and node_id != 'all':
                block_ids.update(descendant_block_ids(course_id, node_id, db))
        if block_ids:
            query = query.filter(ContentChunk.block_id.in_(block_ids))

    # v25.9.12.4: old CMS quiz/problem chunks are allowed as source inside
    # the selected scope. They are not copied directly; prompt + quality checker
    # force generated Learning Check questions to use a different wording/angle.
    # v25.9.12.13: do not silently truncate selected node/course content.
    # Cost Control estimates and course/job limits decide whether the full scope
    # is allowed; the planner must not hide later chunks from GPT.
    return query.order_by(ContentChunk.created_at.asc()).all()


def chunks_to_content(chunks: list[ContentChunk]) -> str:
    def render_chunk(chunk: ContentChunk) -> str:
        problem_note = ''
        if (chunk.source_type or '').lower() == 'problem':
            problem_note = (
                '\nInstruction: Nguồn này là quiz/problem cũ. Được dùng nó như tài liệu nguồn '
                'để hiểu kiến thức chuẩn và đáp án đúng, nhưng BẮT BUỘC tạo câu hỏi mới '
                'bằng cách hỏi khác. Không copy nguyên văn câu hỏi cũ; không giữ nguyên '
                'toàn bộ các đáp án nhiễu nếu chúng chỉ là bản sao của quiz cũ.'
            )
        return (
            f"Source: {chunk.source_ref or chunk.block_id}\n"
            f"Type: {chunk.source_type}\n"
            f"ChunkId: {chunk.id}\n"
            f"BlockId: {chunk.block_id}"
            f"{problem_note}\n"
            f"{chunk.content}"
        )

    return '\n\n---\n\n'.join(render_chunk(chunk) for chunk in chunks)


def concept_aware_content(db: Session, course_id: str, *, content: str, chunks: list[ContentChunk], node_id: str | None, node_title: str | None) -> tuple[str, list[dict]]:
    """Prefix generation content with concept hints without hiding raw source.

    v25.9.14.0 keeps Open edX/native random unchanged, but makes generation
    concept-aware by extracting teachable concepts before the model call.  The
    raw chunks remain below the hint block so source grounding still works.
    """
    if not chunks:
        return content, []
    try:
        concepts, _reused = ConceptService(db).extract_for_chunks(
            course_id=course_id,
            chunks=chunks,
            node_id=node_id if node_id and node_id != 'course' else None,
            node_title=node_title,
            max_concepts=18,
            force=False,
        )
    except Exception:
        # Concept extraction must never block core generation.  It is a pedagogy
        # enhancement; raw source-based generation still continues.
        return content, []
    hint = format_concepts_for_prompt(concepts, max_items=12)
    metadata = [
        {
            'id': c.id,
            'concept_key': c.concept_key,
            'title': c.title,
            'difficulty_hint': c.difficulty_hint,
            'importance_score': c.importance_score,
        }
        for c in concepts
    ]
    if not hint:
        return content, metadata
    return f"{hint}\n\n--- Raw source content below ---\n\n{content}", metadata


def build_generation_content(db: Session, payload: GenerateQuestionsRequest) -> tuple[str, int, list[ContentChunk]]:
    if payload.content and payload.content.strip():
        return payload.content, count_tokens(payload.content), []
    chunks = query_chunks(db, payload.course_id, chunk_ids=payload.chunk_ids, node_ids=payload.node_ids)
    content = chunks_to_content(chunks)
    return content, sum(chunk.token_count for chunk in chunks) or count_tokens(content), chunks


def node_inputs(db: Session, course_id: str, chunks: list[ContentChunk], node_ids: list[str] | None) -> list[dict]:
    title_map = node_title_map(course_id, db)
    selected_ids = [node_id for node_id in (node_ids or []) if node_id and node_id != 'all']

    inputs: list[dict] = []
    for node_id in selected_ids:
        block_ids = descendant_block_ids(course_id, node_id, db)
        node_chunks = [chunk for chunk in chunks if chunk.block_id in block_ids]
        if not node_chunks:
            continue
        meta = title_map.get(node_id, {'title': node_id, 'block_type': 'component', 'path': node_id})
        title = meta.get('path') or meta.get('title') or node_id
        teachable_chunks = []
        skipped_reasons: dict[str, int] = {}
        effective_tokens = 0
        for chunk in node_chunks:
            signal = content_signal(chunk.content, chunk.token_count, title=title, source_type=chunk.source_type)
            if signal.teachable:
                teachable_chunks.append(chunk)
                effective_tokens += signal.effective_tokens
            else:
                skipped_reasons[signal.reason] = skipped_reasons.get(signal.reason, 0) + 1
        inputs.append({
            'node_id': node_id,
            'title': title,
            'block_type': meta.get('block_type') or 'unknown',
            'chunk_count': len(node_chunks),
            'token_count': sum(chunk.token_count for chunk in node_chunks),
            # v25.9.10: use real teachable content for coverage, not intro/admin chunks.
            'teachable_chunk_count': len(teachable_chunks),
            'effective_token_count': effective_tokens,
            'skipped_chunk_count': len(node_chunks) - len(teachable_chunks),
            'skipped_reasons': skipped_reasons,
            'teachable_chunk_ids': [chunk.id for chunk in teachable_chunks],
        })
    return inputs


def _difficulty_percentages(payload: GenerateQuestionsRequest) -> dict[str, float]:
    return payload.difficulty_percentages.as_dict() if payload.difficulty_percentages else {'easy': 50, 'medium': 30, 'hard': 20}


def _split_count_by_difficulty(total: int, percentages: dict[str, float]) -> list[dict]:
    return [row.__dict__ for row in allocate_by_largest_remainder(total, percentages) if row.question_count > 0]


def _split_large_count(count: int, max_batch_size: int) -> list[int]:
    return create_batches(count, max(1, int(max_batch_size or DEFAULT_MAX_QUESTIONS_PER_MODEL_CALL)))


def _difficulty_work_items(
    *,
    course_id: str,
    content: str,
    total_questions: int,
    scope_title: str | None,
    content_tokens: int,
    chunk_ids: list[str],
    node_id: str | None,
    percentages: dict[str, float],
    max_batch_size: int,
    concepts_metadata: list[dict] | None = None,
) -> list[dict]:
    """Build cost-aware work items by difficulty.

    v25.9.8.1 keeps three separate difficulty prompts instead of merging
    remainders into a mixed tail prompt. Example for 50 questions with
    batch_size=12:

        EASY   25 -> primary 12 + 12, delayed EASY tail 1
        MEDIUM 15 -> primary 12,      delayed MEDIUM tail 3
        HARD   10 -> primary 10

    After primary batches finish, the worker adds any missing/failed counts to
    the matching difficulty tail. This preserves the intended ratio and keeps
    prompt caching effective because all difficulty prompts still share the same
    stable prefix and prompt_cache_key.
    """
    items: list[dict] = []
    tail_counts: dict[str, int] = {}
    chunk_hash = sha256_text('\n'.join(sorted(chunk_ids or [])) + '|' + content, 32)
    prompt_cache_key = build_prompt_cache_key(
        course_id=course_id,
        scope_title=scope_title,
        content=content,
        chunk_ids=chunk_ids,
        node_id=node_id,
    )

    def make_item(*, difficulty: str, count: int, phase: str, counts: dict[str, int] | None = None) -> dict:
        normalized_counts = counts or {difficulty: count}
        difficulty_key = difficulty if len(normalized_counts) <= 1 else 'mixed_' + '_'.join(f'{k}{v}' for k, v in sorted(normalized_counts.items()))
        cache_key = build_generation_cache_key(
            prompt_cache_key=prompt_cache_key,
            difficulty=difficulty_key,
            question_count=count,
        )
        return {
            'scope_title': scope_title,
            'question_count': count,
            'content': content,
            'content_tokens': content_tokens or count_tokens(content),
            'chunk_ids': chunk_ids,
            'chunk_hash': chunk_hash,
            'node_id': node_id,
            'prompt_cache_key': prompt_cache_key,
            'generation_cache_key': cache_key,
            'target_difficulty': difficulty,
            'difficulty_counts': normalized_counts,
            'phase': phase,
            'tail_wait_for_primary': phase == 'tail',
            'concepts': concepts_metadata or [],
        }

    for allocation in _split_count_by_difficulty(total_questions, percentages):
        difficulty = str(allocation['difficulty']).lower()
        count = int(allocation['question_count'])
        if count <= 0:
            continue
        if count <= max_batch_size:
            # A normal small difficulty group is not considered a tail. For 20
            # questions default 50/30/20 this remains 10 EASY + 6 MEDIUM + 4 HARD.
            items.append(make_item(difficulty=difficulty, count=count, phase='primary'))
            continue

        full_batches = count // max_batch_size
        remainder = count % max_batch_size
        for _ in range(full_batches):
            items.append(make_item(difficulty=difficulty, count=max_batch_size, phase='primary'))
        if remainder:
            tail_counts[difficulty] = tail_counts.get(difficulty, 0) + remainder

    # Important: do not merge tails from different difficulties into one mixed
    # prompt. The project uses one prompt per difficulty so the tail must keep
    # the same contract: EASY tail uses the EASY prompt, MEDIUM tail uses the
    # MEDIUM prompt, and HARD tail uses the HARD prompt. This avoids ratio drift
    # and still benefits from OpenAI prompt caching because the large static
    # prompt prefix is identical across difficulty calls.
    for difficulty, remainder in tail_counts.items():
        items.append(make_item(
            difficulty=difficulty,
            count=remainder,
            phase='tail',
            counts={difficulty: remainder},
        ))
    return items


def _build_node_work_items(
    db: Session,
    course_id: str,
    chunks: list[ContentChunk],
    node_allocations: list[dict],
    *,
    percentages: dict[str, float],
    max_batch_size: int,
) -> list[dict]:
    work_items: list[dict] = []
    for item in node_allocations:
        count = int(item.get('question_quota') or 0)
        if count <= 0:
            continue
        node_id = str(item.get('node_id') or '')
        block_ids = descendant_block_ids(course_id, node_id, db) if node_id and node_id != 'course' else {chunk.block_id for chunk in chunks}
        node_chunks = [chunk for chunk in chunks if chunk.block_id in block_ids]
        teachable_ids = set(item.get('teachable_chunk_ids') or [])
        if teachable_ids:
            node_chunks = [chunk for chunk in node_chunks if chunk.id in teachable_ids]
        else:
            # Last safety filter: do not send tiny intro/admin chunks to GPT when
            # node coverage is enabled. If everything is filtered out, this node
            # is skipped instead of generating questions from non-learning text.
            node_chunks = [
                chunk for chunk in node_chunks
                if content_signal(chunk.content, chunk.token_count, title=item.get('title') or '', source_type=chunk.source_type).teachable
            ]
        item_content = chunks_to_content(node_chunks)
        if not item_content.strip():
            continue
        item_content, concepts_metadata = concept_aware_content(
            db,
            course_id,
            content=item_content,
            chunks=node_chunks,
            node_id=node_id,
            node_title=item.get('title'),
        )
        item_tokens = sum(chunk.token_count for chunk in node_chunks) or count_tokens(item_content)
        work_items.extend(_difficulty_work_items(
            course_id=course_id,
            content=item_content,
            total_questions=count,
            scope_title=item.get('title'),
            content_tokens=item_tokens,
            chunk_ids=[chunk.id for chunk in node_chunks],
            node_id=node_id,
            percentages=percentages,
            max_batch_size=max_batch_size,
            concepts_metadata=concepts_metadata,
        ))
    return work_items


def _build_batch_work_items(
    course_id: str,
    content: str,
    total_questions: int,
    *,
    percentages: dict[str, float],
    max_batch_size: int,
    scope_title: str | None = None,
) -> list[dict]:
    return _difficulty_work_items(
        course_id=course_id,
        content=content,
        total_questions=total_questions,
        scope_title=scope_title,
        content_tokens=count_tokens(content),
        chunk_ids=[],
        node_id=None,
        percentages=percentages,
        max_batch_size=max_batch_size,
    )


def build_generation_plan(db: Session, payload: GenerateQuestionsRequest) -> GenerationPlan:
    content, content_tokens, chunks = build_generation_content(db, payload)
    safe_batch_size = max(1, min(int(payload.batch_size or DEFAULT_MAX_QUESTIONS_PER_MODEL_CALL), 50))
    percentages = _difficulty_percentages(payload)
    difficulty_allocations = allocation_as_dicts(payload.question_count, percentages)

    node_allocations: list[dict] = []
    work_items: list[dict]

    # Important v24.7/v25.2 behavior:
    # - If teacher selected specific chunks only, do NOT create one call per chunk.
    # - Node coverage is only used when node_ids are explicitly selected.
    # - Difficulty split is applied inside each chosen scope.
    explicit_node_ids = [node_id for node_id in (payload.node_ids or []) if node_id and node_id != 'all']
    if payload.use_node_coverage and not payload.content and explicit_node_ids:
        inputs = node_inputs(db, payload.course_id, chunks, explicit_node_ids)
        node_allocations = [allocation.__dict__ for allocation in NodeCoverageAllocator().allocate(inputs, payload.question_count)]
        work_items = _build_node_work_items(db, payload.course_id, chunks, node_allocations, percentages=percentages, max_batch_size=safe_batch_size)
        if not work_items:
            work_items = _build_batch_work_items(payload.course_id, content, payload.question_count, percentages=percentages, max_batch_size=safe_batch_size)
    else:
        work_items = _build_batch_work_items(payload.course_id, content, payload.question_count, percentages=percentages, max_batch_size=safe_batch_size)

    return GenerationPlan(
        content=content,
        content_tokens=content_tokens,
        chunks=chunks,
        node_allocations=node_allocations,
        difficulty_allocations=difficulty_allocations,
        planned_batches=[int(item.get('question_count') or 0) for item in work_items],
        work_items=work_items,
    )
