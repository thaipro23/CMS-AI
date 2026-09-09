from __future__ import annotations

from typing import Any

from sqlalchemy import case, func

from app.core.openedx_ids import normalize_openedx_course_id, openedx_course_id_candidates
from app.models.course import CourseSyncState
from app.models.question_bank import BankReleaseQuestion, QuestionBankRelease, SubjectChapter, SubjectOffering
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService


_PATCHED = False
_ORIGINAL_OFFERING_STATUS = QuestionBankQuizCreationWorkflowService._offering_published_release_status
_ORIGINAL_LOAD_COURSE_TREE = QuestionBankQuizCreationWorkflowService._load_openedx_sections_for_quiz_detailed
_ORIGINAL_APPLY_AUTO_MAP = QuestionBankQuizCreationWorkflowService.apply_quiz_auto_map


def _chapter_title(service: QuestionBankQuizCreationWorkflowService, chapter: SubjectChapter) -> str:
    return str(service._chapter_display_name(chapter) or '').strip()


def _build_offering_status_cache(
    service: QuestionBankQuizCreationWorkflowService,
    subject_id: str,
) -> dict[str, dict[str, Any]]:
    """Build Release readiness for every version of one subject in bounded queries.

    The legacy selector called status resolution for each version and then for each
    chapter/release, producing an N+1 chain. This preloads all relevant chapters,
    latest published releases and component readiness counts once per preview.
    """
    offerings = (
        service.db.query(SubjectOffering)
        .filter(
            SubjectOffering.subject_id == subject_id,
            SubjectOffering.status.in_(['active', 'draft', 'published', 'approved']),
        )
        .order_by(SubjectOffering.created_at.desc())
        .all()
    )
    offering_ids = [str(item.id) for item in offerings]
    if not offering_ids:
        return {}

    chapters = (
        service.db.query(SubjectChapter)
        .filter(
            SubjectChapter.subject_offering_id.in_(offering_ids),
            SubjectChapter.status == 'active',
        )
        .order_by(
            SubjectChapter.subject_offering_id.asc(),
            SubjectChapter.sort_order.asc(),
            SubjectChapter.chapter_no.asc(),
            SubjectChapter.id.asc(),
        )
        .all()
    )
    chapters_by_offering: dict[str, list[SubjectChapter]] = {}
    for chapter in chapters:
        chapters_by_offering.setdefault(str(chapter.subject_offering_id), []).append(chapter)

    chapter_ids = [str(item.id) for item in chapters]
    latest_release_by_chapter: dict[str, QuestionBankRelease] = {}
    if chapter_ids:
        releases = (
            service.db.query(QuestionBankRelease)
            .filter(
                QuestionBankRelease.chapter_id.in_(chapter_ids),
                QuestionBankRelease.status == 'published',
                QuestionBankRelease.openedx_library_key.isnot(None),
            )
            .order_by(
                QuestionBankRelease.chapter_id.asc(),
                QuestionBankRelease.published_at.desc().nullslast(),
                QuestionBankRelease.created_at.desc(),
                QuestionBankRelease.id.desc(),
            )
            .all()
        )
        for release in releases:
            latest_release_by_chapter.setdefault(str(release.chapter_id), release)

    release_ids = [str(item.id) for item in latest_release_by_chapter.values()]
    component_counts: dict[str, tuple[int, int]] = {}
    if release_ids:
        rows = (
            service.db.query(
                BankReleaseQuestion.bank_release_id,
                func.count(BankReleaseQuestion.id),
                func.sum(
                    case(
                        (func.length(func.trim(BankReleaseQuestion.openedx_library_problem_id)) > 0, 1),
                        else_=0,
                    )
                ),
            )
            .filter(BankReleaseQuestion.bank_release_id.in_(release_ids))
            .group_by(BankReleaseQuestion.bank_release_id)
            .all()
        )
        component_counts = {
            str(release_id): (int(total or 0), int(ready or 0))
            for release_id, total, ready in rows
        }

    statuses: dict[str, dict[str, Any]] = {}
    for offering in offerings:
        details: list[dict[str, Any]] = []
        missing: list[str] = []
        ready_count = 0
        offering_chapters = chapters_by_offering.get(str(offering.id), [])
        for chapter in offering_chapters:
            release = latest_release_by_chapter.get(str(chapter.id))
            total, ready_components = component_counts.get(str(release.id), (0, 0)) if release else (0, 0)
            verified = bool((release.metadata_json or {}).get('verification_complete')) if release else False
            ready = bool(release and total and ready_components == total and verified)
            title = _chapter_title(service, chapter)
            if ready:
                ready_count += 1
            else:
                missing.append(title)
            details.append({
                'chapter_id': chapter.id,
                'chapter_title': title,
                'release_id': release.id if release else None,
                'release_code': release.release_code if release else None,
                'openedx_library_key': release.openedx_library_key if release else None,
                'question_count': total,
                'component_ready_count': ready_components,
                'ready': ready,
            })
        statuses[str(offering.id)] = {
            'all_ready': bool(offering_chapters) and ready_count == len(offering_chapters),
            'chapter_count': len(offering_chapters),
            'ready_chapter_count': ready_count,
            'missing_chapters': missing,
            'details': details,
        }

    service._bank_quiz_offering_status_cache = statuses
    return statuses


def _offering_published_release_status_fast(
    self: QuestionBankQuizCreationWorkflowService,
    offering: SubjectOffering,
) -> dict[str, Any]:
    cache = getattr(self, '_bank_quiz_offering_status_cache', None)
    offering_id = str(offering.id)
    if isinstance(cache, dict) and offering_id in cache:
        return cache[offering_id]

    subject_id = str(getattr(offering, 'subject_id', '') or '')
    if not subject_id:
        return _ORIGINAL_OFFERING_STATUS(self, offering)
    cache = _build_offering_status_cache(self, subject_id)
    return cache.get(offering_id) or _ORIGINAL_OFFERING_STATUS(self, offering)


def _cached_course_blocks(self: QuestionBankQuizCreationWorkflowService, course_id: str) -> tuple[list[dict], list[Any]]:
    canonical_course_id = normalize_openedx_course_id(course_id, required=True)
    candidates = openedx_course_id_candidates(canonical_course_id)
    rows = (
        self.db.query(CourseSyncState)
        .filter(CourseSyncState.course_id.in_(candidates))
        .all()
        if candidates
        else []
    )
    blocks = [
        {
            'block_id': row.block_id,
            'type': row.block_type,
            'display_name': row.display_name,
            'parent_block_id': row.parent_block_id,
            'children': list(getattr(row, 'children', None) or []),
        }
        for row in rows
    ]
    return blocks, rows


async def _load_openedx_sections_fast(
    self: QuestionBankQuizCreationWorkflowService,
    course_id: str,
) -> tuple[list[dict], list[str], dict]:
    """Use locally synced course identity for interactive preview.

    `apply_quiz_auto_map` sets `_bank_quiz_force_live_tree`, so Save still goes
    through the original direct Open edX verification path before persistence.
    """
    if bool(getattr(self, '_bank_quiz_force_live_tree', False)):
        return await _ORIGINAL_LOAD_COURSE_TREE(self, course_id)

    canonical_course_id = normalize_openedx_course_id(course_id, required=True)
    blocks, rows = _cached_course_blocks(self, canonical_course_id)
    if not blocks:
        return await _ORIGINAL_LOAD_COURSE_TREE(self, canonical_course_id)

    sections = [block for block in blocks if str(block.get('type') or '').lower() == 'chapter']
    warnings = [
        'Preview nhanh đang dùng cây course đã sync trong AI Server. Khi Lưu cấu hình, hệ thống sẽ xác minh lại trực tiếp với Open edX.'
    ]
    if not sections:
        sections = [block for block in blocks if str(block.get('type') or '').lower() == 'sequential']
        if sections:
            warnings.append('Course chưa có Section/chapter rõ ràng trong cache; đang tạm dùng Subsection để map.')
    return sections, warnings, {
        'source': 'cached',
        'course_id': canonical_course_id,
        'error_code': None,
        'direct_error': None,
        'cached_block_count': len(rows),
    }


async def _apply_quiz_auto_map_live(self: QuestionBankQuizCreationWorkflowService, *args, **kwargs):
    previous = bool(getattr(self, '_bank_quiz_force_live_tree', False))
    self._bank_quiz_force_live_tree = True
    try:
        return await _ORIGINAL_APPLY_AUTO_MAP(self, *args, **kwargs)
    finally:
        self._bank_quiz_force_live_tree = previous


def apply_bank_quiz_performance_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    QuestionBankQuizCreationWorkflowService._offering_published_release_status = _offering_published_release_status_fast
    QuestionBankQuizCreationWorkflowService._load_openedx_sections_for_quiz_detailed = _load_openedx_sections_fast
    QuestionBankQuizCreationWorkflowService.apply_quiz_auto_map = _apply_quiz_auto_map_live
    _PATCHED = True
