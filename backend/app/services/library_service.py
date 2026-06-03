import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

from app.algorithms.course_tree import CourseTreeBuilder, CourseTreeNode
from app.models.course import ContentChunk, CourseLibrary, CourseSyncState
from app.models.question import Question

CHAPTER_TYPES = {'chapter', 'section', 'module', 'learning_module', 'week'}
FALLBACK_STRUCTURAL_TYPES = {'sequential', 'subsection', 'section', 'module', 'chapter', 'learning_module', 'week'}
COMPONENT_TYPES = {'vertical', 'html', 'video', 'problem', 'file', 'pdf', 'component'}
DIFFICULTIES = {'easy', 'medium', 'hard'}


@dataclass
class LibraryTarget:
    source_node_id: str | None
    source_node_title: str | None
    chapter_node_id: str
    chapter_title: str
    difficulty: str
    library: CourseLibrary


class ChapterLibraryService:
    """Resolve Unit/PDF/Video/HTML nodes to their parent Chapter/Module + Difficulty Library."""

    def __init__(self, db: Session):
        self.db = db

    def _states_to_blocks(self, course_id: str) -> list[dict]:
        states = self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()
        return [{
            'block_id': state.block_id,
            'parent_block_id': state.parent_block_id,
            'type': state.block_type,
            'display_name': state.display_name,
        } for state in states]

    def _all_nodes(self, course_id: str) -> dict[str, CourseTreeNode]:
        roots = CourseTreeBuilder().build(self._states_to_blocks(course_id))
        return {node.node_id: node for node in CourseTreeBuilder().traverse(roots)}

    def _course_code(self, course_id: str) -> str:
        if 'course-v1:' in course_id and '+' in course_id:
            parts = course_id.split(':', 1)[1].split('+')
            if len(parts) >= 2 and parts[1].strip():
                return parts[1].strip()
        parts = course_id.split('+')
        return parts[1].strip() if len(parts) >= 2 and parts[1].strip() else course_id.rsplit('/', 1)[-1]

    def _slug(self, text: str) -> str:
        text = unicodedata.normalize('NFKD', (text or '').strip().lower()).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')[:80] or 'chapter'

    def _is_chapter_like(self, node: CourseTreeNode | None) -> bool:
        if not node:
            return False
        block_type = (node.block_type or '').strip().lower()
        title = (node.title or '').strip().lower()
        if block_type in CHAPTER_TYPES:
            return True
        return any(keyword in title for keyword in ['chapter', 'module', 'week', 'chương', 'chuong', 'bài ', 'bai ', 'phần ', 'phan '])

    def _path_to_root(self, nodes: dict[str, CourseTreeNode], node: CourseTreeNode | None) -> list[CourseTreeNode]:
        path: list[CourseTreeNode] = []
        current = node
        seen: set[str] = set()
        while current and current.node_id not in seen:
            path.append(current)
            seen.add(current.node_id)
            current = nodes.get(current.parent_id or '') if current.parent_id else None
        return path

    def _normalize_difficulty(self, difficulty: str | None) -> str:
        value = (difficulty or 'easy').strip().lower()
        return value if value in DIFFICULTIES else 'easy'

    def display_name(self, course_id: str, chapter_title: str, difficulty: str | None = None) -> str:
        diff = self._normalize_difficulty(difficulty).upper()
        return f'{self._course_code(course_id)} - {chapter_title or "Chapter"} - {diff}'

    def find_chapter_for_node(self, course_id: str, source_node_id: str | None) -> tuple[CourseTreeNode | None, CourseTreeNode | None]:
        """Resolve source node to the best Chapter/Module-level library scope.

        Open edX courses are not always shaped as course -> chapter -> sequential
        -> vertical. Some real courses use section/module/week names or miss a
        chapter block entirely. We therefore prefer a true chapter-like ancestor;
        if none exists, we fall back to the first meaningful structural node under
        the course instead of publishing to the component/unit itself.
        """
        nodes = self._all_nodes(course_id)
        source = nodes.get(source_node_id or '') if source_node_id else None
        if source and self._is_chapter_like(source):
            return source, source

        path = self._path_to_root(nodes, source)
        for node in path:
            if self._is_chapter_like(node):
                return node, source

        root_to_source = list(reversed(path))
        for node in root_to_source:
            block_type = (node.block_type or '').strip().lower()
            if block_type in FALLBACK_STRUCTURAL_TYPES and block_type not in COMPONENT_TYPES:
                return node, source

        # If source is missing or not in the tree, use a course-level first
        # chapter/module if available. This keeps the publisher deterministic.
        for node in nodes.values():
            if self._is_chapter_like(node):
                return node, source
        for node in nodes.values():
            if (node.block_type or '').strip().lower() in FALLBACK_STRUCTURAL_TYPES:
                return node, source
        return None, source

    def ensure_library_for_chapter(self, course_id: str, chapter_node_id: str, chapter_title: str, difficulty: str | None = None) -> CourseLibrary:
        normalized_difficulty = self._normalize_difficulty(difficulty)
        existing = self.db.query(CourseLibrary).filter(
            CourseLibrary.course_id == course_id,
            CourseLibrary.chapter_node_id == chapter_node_id,
            CourseLibrary.difficulty == normalized_difficulty,
        ).first()
        display_name = self.display_name(course_id, chapter_title, normalized_difficulty)
        if existing:
            existing.chapter_title = chapter_title or existing.chapter_title
            existing.difficulty = normalized_difficulty
            existing.display_name = display_name
            existing.updated_at = datetime.utcnow()
            self.db.flush()
            return existing
        library = CourseLibrary(
            course_id=course_id,
            chapter_node_id=chapter_node_id,
            chapter_title=chapter_title or chapter_node_id,
            difficulty=normalized_difficulty,
            display_name=display_name,
            library_key=f'{self._course_code(course_id)}-{self._slug(chapter_title or chapter_node_id)}-{normalized_difficulty}',
            status='local_ready',
            metadata_json={
                'architecture': 'course_many_libraries_by_chapter_and_difficulty',
                'chapter_node_id': chapter_node_id,
                'difficulty': normalized_difficulty,
            },
        )
        self.db.add(library)
        self.db.flush()
        return library

    def resolve_target(self, course_id: str, source_node_id: str | None, source_node_title: str | None = None, difficulty: str | None = None) -> LibraryTarget | None:
        normalized_difficulty = self._normalize_difficulty(difficulty)
        chapter, source = self.find_chapter_for_node(course_id, source_node_id)
        if not chapter:
            return None
        library = self.ensure_library_for_chapter(course_id, chapter.node_id, chapter.title, normalized_difficulty)
        return LibraryTarget(
            source_node_id=source.node_id if source else source_node_id,
            source_node_title=source.title if source else source_node_title,
            chapter_node_id=chapter.node_id,
            chapter_title=chapter.title,
            difficulty=normalized_difficulty,
            library=library,
        )

    def resolve_question_target(self, question: Question) -> LibraryTarget | None:
        source_node_id = question.source_node_id or question.block_id
        if not source_node_id and question.source_chunk_id:
            chunk = self.db.get(ContentChunk, question.source_chunk_id)
            if chunk:
                source_node_id = chunk.block_id
        return self.resolve_target(question.course_id, source_node_id, question.source_node_title, question.difficulty)

    def list_libraries(self, course_id: str | None = None) -> list[CourseLibrary]:
        query = self.db.query(CourseLibrary)
        if course_id:
            query = query.filter(CourseLibrary.course_id == course_id)
        return query.order_by(CourseLibrary.course_id.asc(), CourseLibrary.chapter_title.asc(), CourseLibrary.difficulty.asc()).all()
