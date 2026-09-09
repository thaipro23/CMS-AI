from __future__ import annotations

import re

from app.core.openedx_ids import normalize_openedx_course_id, openedx_course_id_candidates
from app.models.question_bank import EdxCourseChapterMapping, EdxCourseMapping, SubjectChapter
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService


_PATCHED = False
_ORIGINAL_LOAD = QuestionBankQuizCreationWorkflowService._load_openedx_sections_for_quiz_detailed


def _node_type(node_id: str) -> str:
    match = re.search(r'\+type@([^+]+)', str(node_id or ''))
    value = str(match.group(1) if match else '').strip().lower()
    return value if value in {'chapter', 'sequential'} else 'chapter'


async def _load_sections_from_saved_mapping_first(
    self: QuestionBankQuizCreationWorkflowService,
    course_id: str,
):
    # Save/apply must retain the live Open edX verification contract installed by
    # bank_quiz_performance.py. This fast path is interactive preview only.
    if bool(getattr(self, '_bank_quiz_force_live_tree', False)):
        return await _ORIGINAL_LOAD(self, course_id)

    canonical = normalize_openedx_course_id(course_id, required=True)
    candidates = openedx_course_id_candidates(canonical)
    mapping = (
        self.db.query(EdxCourseMapping)
        .filter(EdxCourseMapping.openedx_course_id.in_(candidates))
        .order_by(EdxCourseMapping.updated_at.desc().nullslast(), EdxCourseMapping.created_at.desc().nullslast())
        .first()
        if candidates else None
    )
    if mapping:
        rows = (
            self.db.query(EdxCourseChapterMapping, SubjectChapter)
            .join(SubjectChapter, SubjectChapter.id == EdxCourseChapterMapping.subject_chapter_id)
            .filter(
                EdxCourseChapterMapping.course_mapping_id == mapping.id,
                EdxCourseChapterMapping.enabled.is_(True),
                EdxCourseChapterMapping.openedx_parent_node_id.isnot(None),
            )
            .order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc(), SubjectChapter.id.asc())
            .all()
        )
        if rows:
            sections = []
            seen: set[str] = set()
            for saved, chapter in rows:
                node_id = str(saved.openedx_parent_node_id or '').strip()
                if not node_id or node_id in seen:
                    continue
                seen.add(node_id)
                sections.append({
                    'block_id': node_id,
                    'type': _node_type(node_id),
                    'display_name': str(self._chapter_display_name(chapter) or chapter.title or node_id),
                    'parent_block_id': None,
                    'children': [],
                })
            if sections:
                return sections, [
                    'Preview nhanh đang dùng mapping Course CMS đã lưu. Khi bấm Lưu cấu hình, hệ thống xác minh lại trực tiếp với Open edX.'
                ], {
                    'source': 'cached',
                    'course_id': canonical,
                    'error_code': None,
                    'direct_error': None,
                    'cached_block_count': len(sections),
                    'cache_kind': 'saved_course_mapping',
                }

    # No saved mapping: fall through to the existing cache-first implementation,
    # which may contact Open edX only when CourseSyncState is also empty.
    return await _ORIGINAL_LOAD(self, canonical)


def apply_bank_quiz_saved_mapping_fastpath() -> None:
    global _PATCHED
    if _PATCHED:
        return
    QuestionBankQuizCreationWorkflowService._load_openedx_sections_for_quiz_detailed = _load_sections_from_saved_mapping_first
    _PATCHED = True
