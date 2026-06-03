from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.models.course import CourseSyncState, ContentChunk
from app.services.hash_service import content_hash
from app.services.chunker import Chunker
from app.services.token_counter import count_tokens
from app.services.content_extractor import ContentExtractor, ExtractedContent
from app.algorithms.course_tree import CourseTreeBuilder


class CourseSyncService:
    """Sync normalized Open edX course content into AI Server.

    v16-v19 upgrades:
    - builds course tree order from Open edX children/parent relationships;
    - extracts HTML/transcript/file-like content through ContentExtractor;
    - uses hash-based change detection per component;
    - chunks only changed content while preserving source references;
    - v20 uses Open edX nodes directly instead of inferred topics.

    v25.9.12.6 hardens sync against stale duplicated chunks:
    - the sync fingerprint now includes the parser/chunk-policy version so a code
      upgrade can re-materialize chunks even when the upstream raw content did
      not change;
    - suspicious problem nodes that should fit into a single chunk but currently
      have many stored chunks are auto-repaired on the next sync without
      requiring manual SQL cleanup.
    """

    def __init__(self, db: Session):
        self.db = db
        self.chunker = Chunker()
        self.extractor = ContentExtractor()
        self.tree_builder = CourseTreeBuilder()

    def sync_blocks(self, course_id: str, blocks: list[dict], force: bool = False) -> tuple[int, int]:
        # Build a stable, de-duplicated course order. The mock connector and
        # some Open edX payloads may expose both parent links and children links;
        # the tree builder removes duplicated traversal paths.
        ordered_blocks = self.tree_builder.flatten_blocks(blocks)
        extracted_items = self.extractor.extract_blocks(ordered_blocks)
        changed = 0

        # v25.9.12.7: when force-syncing after a parser/chunker bug, remove all
        # previously stored problem chunks for the course up front.  They are
        # deterministic derived data and will be recreated below from the current
        # Studio XML.  This also fixes cases where the user deleted one old block
        # id but the real/current problem block id is different.
        if force:
            self._delete_course_problem_chunks(course_id)

        for item in extracted_items:
            state = self._upsert_state(course_id, item)
            new_hash = self._sync_fingerprint(item)
            is_changed = force or state.content_hash != new_hash or self._needs_chunk_repair(course_id, item)
            if is_changed:
                changed += 1
                state.content_hash = new_hash
                state.sync_status = 'changed'
                state.last_synced_at = datetime.utcnow()
                self._replace_chunks(course_id, item)
            else:
                state.sync_status = 'synced'

        # Also record non-text container blocks so tree/state dashboard remains visible.
        known_block_ids = {item.block_id for item in extracted_items}
        for block in ordered_blocks:
            block_id = block.get('block_id') or block.get('id')
            if not block_id or block_id in known_block_ids:
                continue
            state = self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == block_id).first()
            if state is None:
                state = CourseSyncState(course_id=course_id, block_id=block_id, block_type=block.get('type', 'unknown'), display_name=block.get('display_name', ''))
                self.db.add(state)
            state.parent_block_id = block.get('parent_block_id') or block.get('parent')
            state.block_type = block.get('type', 'unknown')
            state.display_name = block.get('display_name', '')
            state.sync_status = state.sync_status or 'container'

        self.db.commit()
        # v20: No automatic topic extraction. Generation/filtering uses the
        # Open edX course nodes directly, so sync stops after course tree + chunks.
        return len(ordered_blocks), changed

    def _upsert_state(self, course_id: str, item: ExtractedContent) -> CourseSyncState:
        state = self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == item.block_id).first()
        if state is None:
            state = CourseSyncState(course_id=course_id, block_id=item.block_id, block_type=item.block_type, display_name=item.display_name)
            self.db.add(state)
        state.parent_block_id = item.parent_block_id
        state.block_type = item.block_type
        state.display_name = item.display_name
        return state


    def _delete_course_problem_chunks(self, course_id: str) -> None:
        problem_block_ids = [
            row[0]
            for row in self.db.query(CourseSyncState.block_id).filter(
                CourseSyncState.course_id == course_id,
                CourseSyncState.block_type == 'problem',
            ).all()
        ]
        if problem_block_ids:
            self.db.query(ContentChunk).filter(
                ContentChunk.course_id == course_id,
                ContentChunk.block_id.in_(problem_block_ids),
            ).delete(synchronize_session=False)

    def _sync_fingerprint(self, item: ExtractedContent) -> str:
        max_tokens, overlap_tokens = self._chunk_policy(item)
        signature = (
            'v25.9.13.14'
            f'|source_type={item.source_type or item.block_type}'
            f'|max_tokens={max_tokens}'
            f'|overlap_tokens={overlap_tokens}'
            f'|content={item.content}'
        )
        return content_hash(signature)

    def _needs_chunk_repair(self, course_id: str, item: ExtractedContent) -> bool:
        existing = self.db.query(ContentChunk).filter(
            ContentChunk.course_id == course_id,
            ContentChunk.block_id == item.block_id,
        ).all()
        if not existing:
            return False

        max_tokens, _ = self._chunk_policy(item)
        expected_single_chunk = (item.source_type or item.block_type or '').lower() == 'problem' and count_tokens(item.content) <= max_tokens
        if not expected_single_chunk:
            return False

        if len(existing) != 1:
            return True

        stored = existing[0]
        stored_tokens = stored.token_count or 0
        expected_tokens = count_tokens(item.content)
        # Heal clearly stale/problematic rows where one problem node shows far
        # more content than the freshly extracted parser output.
        return stored_tokens > max(expected_tokens * 2, expected_tokens + 500)

    def _chunk_policy(self, item: ExtractedContent) -> tuple[int, int]:
        """Choose chunk size by source type while preserving CMS node identity.

        A CMS/XBlock node is still one node even when its text is split into multiple
        chunks for AI context windows.  Old quiz/problem XML often lands just above
        the generic chunk size, which made a single CMS problem look like two
        separate pieces in the UI.  Problem blocks therefore get a larger,
        non-overlapping chunk size so normal quizzes remain one chunk while very
        large banks can still be split safely.
        """
        source_type = (item.source_type or item.block_type or '').lower()
        if source_type == 'problem':
            # Keep a CMS problem block as one source chunk.  A problem may contain
            # multiple questions, including checkboxgroup/choiceresponse, but it is
            # still one CMS node and should not explode into hundreds of chunks.
            return 8000, 0
        if source_type == 'transcript':
            return 900, 120
        if source_type in {'file', 'pdf', 'pptx', 'ppt', 'docx', 'xlsx', 'xlsm', 'csv', 'tsv', 'txt', 'md', 'markdown', 'html', 'json', 'xml', 'srt', 'vtt'}:
            return 1000, 120
        return 900, 100

    def _replace_chunks(self, course_id: str, item: ExtractedContent) -> None:
        self.db.query(ContentChunk).filter(ContentChunk.course_id == course_id, ContentChunk.block_id == item.block_id).delete()
        if not item.content:
            return
        max_tokens, overlap_tokens = self._chunk_policy(item)
        source_type = (item.source_type or item.block_type or '').lower()
        # Problem parser formats questions/options on separate lines and marks the
        # correct answer for teacher/admin UI.  Preserve that formatting when the
        # whole problem fits one context chunk; generic word-joining would make the
        # Node Detail hard to read and highlight too much text.
        if source_type == 'problem':
            chunks = [item.content]
        else:
            chunks = self.chunker.chunk_text(item.content, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        for index, chunk in enumerate(chunks, start=1):
            source_ref = item.source_ref or item.block_id
            if item.timestamp_start or item.timestamp_end:
                source_ref = f'{source_ref}#t={item.timestamp_start or ""}-{item.timestamp_end or ""}'
            if len(chunks) > 1:
                source_ref = f'{source_ref}#chunk={index}'
            self.db.add(ContentChunk(
                course_id=course_id,
                block_id=item.block_id,
                content=chunk,
                token_count=count_tokens(chunk),
                source_type=item.source_type,
                page_number=item.page_number,
                timestamp_start=item.timestamp_start,
                timestamp_end=item.timestamp_end,
                source_ref=source_ref,
            ))
