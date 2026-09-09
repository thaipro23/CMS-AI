from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sqlalchemy import func

from app.models.academic import (
    AcademicClass,
    AcademicClassStudent,
    AcademicCourseMapping,
    AcademicStudentLearningSnapshot,
)
from app.services.academic_service import AcademicService


_PATCHED = False
_OVERVIEW_MODE: ContextVar[bool] = ContextVar('academic_subject_overview_fast_mode', default=False)
_ORIGINAL_LIST_TEACHER_SUBJECTS = AcademicService.list_teacher_subjects
_ORIGINAL_LEARNING_SUMMARY_BY_CLASS_IDS = AcademicService._learning_summary_by_class_ids
_ORIGINAL_INHERITED_MAPPINGS = AcademicService.inherited_course_mappings_for_classes


def _percent(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if 0 <= number <= 1:
        number *= 100.0
    return round(number, 2)


def _learning_summary_by_class_ids_fast(
    self: AcademicService,
    class_ids: list[str],
    course_by_class: dict[str, str | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Lightweight subject-overview learning summary.

    The full helper hydrates every AcademicStudentLearningSnapshot including
    potentially large raw_json payloads, then builds component-level summaries
    that the subject-management screen never renders. PTCĐ / all campuses can
    span thousands of learners, so that unnecessary JSON transfer/parsing makes
    a simple subject list take many seconds and can exhaust the request timeout.

    This overview path selects only canonical columns already persisted on the
    snapshot. Class detail / analytics keep the original richer helper.
    """
    if not _OVERVIEW_MODE.get():
        return _ORIGINAL_LEARNING_SUMMARY_BY_CLASS_IDS(self, class_ids, course_by_class)
    if not class_ids:
        return {}

    totals = {
        str(class_id): int(count or 0)
        for class_id, count in self.db.query(
            AcademicClassStudent.class_id,
            func.count(AcademicClassStudent.id),
        ).filter(
            AcademicClassStudent.class_id.in_(class_ids)
        ).group_by(AcademicClassStudent.class_id).all()
    }

    expected_courses = {str(course) for course in (course_by_class or {}).values() if course}
    query = self.db.query(
        AcademicStudentLearningSnapshot.class_id,
        AcademicStudentLearningSnapshot.openedx_course_id,
        AcademicStudentLearningSnapshot.enrollment_status,
        AcademicStudentLearningSnapshot.progress_percent,
        AcademicStudentLearningSnapshot.grade_percent,
        AcademicStudentLearningSnapshot.completed_blocks,
        AcademicStudentLearningSnapshot.last_activity_at,
        AcademicStudentLearningSnapshot.learning_synced_at,
        AcademicStudentLearningSnapshot.last_synced_at,
    ).filter(AcademicStudentLearningSnapshot.class_id.in_(class_ids))
    if expected_courses:
        query = query.filter(AcademicStudentLearningSnapshot.openedx_course_id.in_(sorted(expected_courses)))

    buckets: dict[str, dict[str, Any]] = {
        str(class_id): {
            'synced': 0,
            'enrolled': 0,
            'active': 0,
            'progress_sum': 0.0,
            'progress_count': 0,
            'grade_sum': 0.0,
            'grade_count': 0,
            'last_synced_at': None,
        }
        for class_id in class_ids
    }

    for (
        class_id,
        openedx_course_id,
        enrollment_status,
        progress_percent,
        grade_percent,
        completed_blocks,
        last_activity_at,
        learning_synced_at,
        last_synced_at,
    ) in query.all():
        class_key = str(class_id)
        expected = str((course_by_class or {}).get(class_key) or '')
        if expected and str(openedx_course_id or '') != expected:
            continue
        bucket = buckets.setdefault(class_key, {
            'synced': 0, 'enrolled': 0, 'active': 0,
            'progress_sum': 0.0, 'progress_count': 0,
            'grade_sum': 0.0, 'grade_count': 0,
            'last_synced_at': None,
        })
        bucket['synced'] += 1
        enrolled = str(enrollment_status or '').strip().lower() == 'enrolled'
        if enrolled:
            bucket['enrolled'] += 1
        progress = _percent(progress_percent)
        grade = _percent(grade_percent)
        if progress is not None:
            bucket['progress_sum'] += progress
            bucket['progress_count'] += 1
        if grade is not None:
            bucket['grade_sum'] += grade
            bucket['grade_count'] += 1
        if enrolled and (
            (progress is not None and progress > 0)
            or grade is not None
            or int(completed_blocks or 0) > 0
            or last_activity_at is not None
        ):
            bucket['active'] += 1
        sync_at = learning_synced_at or last_synced_at
        if sync_at and (bucket['last_synced_at'] is None or sync_at > bucket['last_synced_at']):
            bucket['last_synced_at'] = sync_at

    result: dict[str, dict[str, Any]] = {}
    for class_id in class_ids:
        key = str(class_id)
        bucket = buckets.get(key) or {}
        total = int(totals.get(key, 0) or 0)
        synced = int(bucket.get('synced', 0) or 0)
        enrolled = int(bucket.get('enrolled', 0) or 0)
        active = int(bucket.get('active', 0) or 0)
        progress_count = int(bucket.get('progress_count', 0) or 0)
        grade_count = int(bucket.get('grade_count', 0) or 0)
        avg_progress = round(float(bucket.get('progress_sum', 0.0)) / progress_count, 2) if progress_count else None
        avg_grade = round(float(bucket.get('grade_sum', 0.0)) / grade_count, 2) if grade_count else None
        course_id = (course_by_class or {}).get(key)
        result[key] = {
            'learning_enrolled_count': enrolled,
            'learning_active_count': active,
            'learning_synced_count': synced,
            'learning_not_enrolled_count': max(0, total - enrolled),
            'learning_status_counts': {},
            'learning_avg_progress_percent': avg_progress,
            'learning_avg_grade_percent': avg_grade,
            'learning_last_synced_at': bucket.get('last_synced_at'),
            'learning_component_summaries': [],
            'learning_alerts': self._learning_alerts_from_summary(
                total=total,
                enrolled=enrolled,
                synced=synced,
                active=active,
                avg_progress=avg_progress,
                avg_grade=avg_grade,
                course_id=course_id,
            ),
        }
    return result


def _inherited_course_mappings_for_classes_fast(
    self: AcademicService,
    classes: list[AcademicClass],
) -> dict[str, AcademicCourseMapping]:
    """Exact existing mapping precedence without classes × all mappings scan."""
    valid_classes = [cls for cls in classes if cls and cls.id and cls.term_id and cls.subject_id]
    if not valid_classes:
        return {}
    term_ids = {cls.term_id for cls in valid_classes}
    subject_ids = {cls.subject_id for cls in valid_classes}
    mappings = self.db.query(AcademicCourseMapping).filter(
        AcademicCourseMapping.term_id.in_(term_ids),
        AcademicCourseMapping.subject_id.in_(subject_ids),
        AcademicCourseMapping.active.is_(True),
    ).order_by(
        AcademicCourseMapping.updated_at.desc().nullslast(),
        AcademicCourseMapping.created_at.desc().nullslast(),
    ).all()

    by_scope: dict[tuple[str, str], list[AcademicCourseMapping]] = {}
    for mapping in mappings:
        by_scope.setdefault((str(mapping.term_id), str(mapping.subject_id)), []).append(mapping)

    result: dict[str, AcademicCourseMapping] = {}
    for cls in valid_classes:
        candidates = by_scope.get((str(cls.term_id), str(cls.subject_id)), [])
        priorities = [
            (cls.block_id, cls.campus, cls.branch),
            (cls.block_id, None, cls.branch),
            (cls.block_id, cls.campus, None),
            (cls.block_id, None, None),
            (None, cls.campus, cls.branch),
            (None, None, cls.branch),
            (None, cls.campus, None),
            (None, None, None),
        ]
        rank_by_scope = {scope: rank for rank, scope in enumerate(priorities)}
        best: AcademicCourseMapping | None = None
        best_rank: int | None = None
        for mapping in candidates:
            rank = rank_by_scope.get((mapping.block_id, mapping.campus, mapping.branch))
            if rank is None:
                continue
            if best_rank is None or rank < best_rank:
                best = mapping
                best_rank = rank
                if rank == 0:
                    break
        if best is not None:
            result[str(cls.id)] = best
    return result


def _list_teacher_subjects_fast(self: AcademicService, user, *args, **kwargs):
    platform = str(kwargs.get('learning_platform') or 'cms').strip().lower()
    token = _OVERVIEW_MODE.set(platform == 'cms')
    try:
        return _ORIGINAL_LIST_TEACHER_SUBJECTS(self, user, *args, **kwargs)
    finally:
        _OVERVIEW_MODE.reset(token)


def apply_academic_subject_overview_performance_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    AcademicService._learning_summary_by_class_ids = _learning_summary_by_class_ids_fast
    AcademicService.inherited_course_mappings_for_classes = _inherited_course_mappings_for_classes_fast
    AcademicService.list_teacher_subjects = _list_teacher_subjects_fast
    _PATCHED = True
