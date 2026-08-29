from __future__ import annotations

import math
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import AcademicClass, AcademicClassStudent, AcademicStudent, AcademicStudentLearningSnapshot, OpenEdXUserMapping
from app.services.academic.helpers import _page
from app.services.training_policy_service import TrainingPolicyService


class AcademicRosterWorkflowService:
    """Class roster/student detail workflow extracted from AcademicService.

    The workflow remains API-compatible with the legacy AcademicService method but
    localizes roster query, learning-status filtering, assignment score hydration,
    and row shaping. Heavy publish/sync/enrollment flows are intentionally not
    moved here.
    """

    def __init__(self, db: Session, parent: Any):
        self.db = db
        self.parent = parent

    def list_class_students(
        self,
        user: UserContext,
        class_id: str,
        *,
        search: str | None = None,
        learning_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        self.parent.assert_can_access_class(user, class_id)
        page, page_size = _page(page, page_size)
        cls = self.db.get(AcademicClass, class_id)
        effective_mapping = self.parent.effective_course_mapping_for_class(cls) if cls else None
        course_id = effective_mapping.openedx_course_id if effective_mapping else None
        query = self.db.query(
            AcademicStudent,
            AcademicClassStudent,
            OpenEdXUserMapping,
            AcademicStudentLearningSnapshot,
        ).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(
            OpenEdXUserMapping,
            OpenEdXUserMapping.student_id == AcademicStudent.id,
        ).outerjoin(
            AcademicStudentLearningSnapshot,
            and_(
                AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                AcademicStudentLearningSnapshot.class_id == class_id,
                AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            ),
        ).filter(AcademicClassStudent.class_id == class_id)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicStudent.student_code.ilike(like),
                AcademicStudent.username.ilike(like),
                AcademicStudent.full_name.ilike(like),
                AcademicStudent.email.ilike(like),
                OpenEdXUserMapping.openedx_username.ilike(like),
            ))
        status_filter = str(learning_status or '').strip().lower()
        if status_filter and status_filter not in {'all', 'tat_ca'}:
            query = self._apply_learning_status_filter(query, status_filter)
        total = query.count()
        rows = query.order_by(
            AcademicStudent.student_code.asc().nullslast(),
            AcademicStudent.username.asc(),
        ).offset((page - 1) * page_size).limit(page_size).all()
        block = self.parent._block_for_class(cls) if cls else None
        policy_service = TrainingPolicyService(self.db)
        page_student_ids = [student.id for student, _class_student, _mapping, _learning in rows]
        assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id, page_student_ids)
        deadline_overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
        page_component_scores: list[dict[str, Any]] = []
        for _student, _class_student, _mapping, learning in rows:
            page_component_scores.extend(self.parent._component_scores_from_snapshot(learning))
        quiz_schedule_by_number = self.parent._quiz_schedule_map_for_class(cls, page_component_scores) if cls else {}
        for number, override in (deadline_overrides or {}).items():
            if not override:
                continue
            existing = quiz_schedule_by_number.get(int(number), {})
            quiz_schedule_by_number[int(number)] = {
                **existing,
                'quiz_numbers': existing.get('quiz_numbers') or [int(number)],
                'from_date': override.start_date.isoformat() if override.start_date else existing.get('from_date'),
                'due_date': override.deadline_date.isoformat() if override.deadline_date else existing.get('due_date'),
                'deadline_mode': 'quiz_deadline_configured' if override.deadline_date else existing.get('deadline_mode'),
                'schedule_warning': None if override.deadline_date else existing.get('schedule_warning'),
            }
        items = [
            self.parent._student_mapping_item(
                class_id,
                student,
                class_student.synced_at,
                mapping,
                learning,
                class_student,
                cls=cls,
                block=block,
                policy_service=policy_service,
                assignment_scores=assignment_scores,
                deadline_overrides=deadline_overrides,
                course_id=course_id,
                quiz_schedule_by_number=quiz_schedule_by_number,
            )
            for student, class_student, mapping, learning in rows
        ]
        total_pages = math.ceil(total / page_size) if total else 0
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
        }

    def _apply_learning_status_filter(self, query: Any, status_filter: str) -> Any:
        if status_filter == 'cms_not_synced':
            return query.filter(or_(OpenEdXUserMapping.id.is_(None), OpenEdXUserMapping.match_status != 'matched'))
        if status_filter == 'not_enrolled':
            return query.filter(or_(
                AcademicStudentLearningSnapshot.id.is_(None),
                AcademicStudentLearningSnapshot.enrollment_status != 'enrolled',
            ))
        if status_filter == 'no_activity':
            return query.filter(or_(
                AcademicStudentLearningSnapshot.id.is_(None),
                and_(
                    AcademicStudentLearningSnapshot.enrollment_status == 'enrolled',
                    AcademicStudentLearningSnapshot.progress_percent.is_(None),
                    AcademicStudentLearningSnapshot.grade_percent.is_(None),
                ),
                and_(
                    AcademicStudentLearningSnapshot.enrollment_status == 'enrolled',
                    AcademicStudentLearningSnapshot.progress_percent <= 0,
                    AcademicStudentLearningSnapshot.grade_percent.is_(None),
                ),
            ))
        if status_filter == 'low_progress':
            return query.filter(
                AcademicStudentLearningSnapshot.progress_percent.isnot(None),
                AcademicStudentLearningSnapshot.progress_percent < self.parent._low_progress_threshold(),
            )
        if status_filter == 'low_grade':
            return query.filter(
                AcademicStudentLearningSnapshot.grade_percent.isnot(None),
                AcademicStudentLearningSnapshot.grade_percent < self.parent._low_grade_threshold(),
            )
        if status_filter == 'sync_error':
            return query.filter(or_(
                AcademicStudentLearningSnapshot.enrollment_status.in_(['failed', 'unknown', 'missing_user', 'inactive_user']),
                OpenEdXUserMapping.match_status.in_(['inactive', 'ambiguous', 'manual_required']),
            ))
        return query
