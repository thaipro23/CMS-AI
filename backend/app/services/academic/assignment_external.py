from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.academic import AcademicAssignmentDefenseScore, AcademicClassStudent, AcademicStudent


ASSIGNMENT_SCORE_EXTERNAL_MESSAGE = (
    'Workflow nhập/sửa điểm Assignment đã tắt trên AI Server. '
    'Điểm Assignment do hệ thống khác xử lý; AI Server chỉ đọc/hiển thị dữ liệu đã được đồng bộ nếu có.'
)


class AcademicAssignmentExternalWorkflowService:
    """Read-only assignment/defense score facade.

    v25.9.16.7.2.64.12 removes manual assignment score entry from AI Server.
    The external assignment/defense system is the source of truth.  This service
    keeps a read-only list endpoint for backward compatibility and blocks all
    write attempts with HTTP 410 so old clients fail safely.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_class_assignment_scores(
        self,
        *,
        class_id: str,
        course_id: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        score_join_conditions = [
            AcademicAssignmentDefenseScore.class_id == AcademicClassStudent.class_id,
            AcademicAssignmentDefenseScore.student_id == AcademicClassStudent.student_id,
        ]
        if course_id:
            score_join_conditions.append(or_(
                AcademicAssignmentDefenseScore.course_id == course_id,
                AcademicAssignmentDefenseScore.course_id.is_(None),
            ))
        rows = self.db.query(AcademicClassStudent, AcademicStudent, AcademicAssignmentDefenseScore).join(
            AcademicStudent,
            AcademicStudent.id == AcademicClassStudent.student_id,
        ).outerjoin(
            AcademicAssignmentDefenseScore,
            and_(*score_join_conditions),
        ).filter(AcademicClassStudent.class_id == class_id).order_by(
            AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()
        ).offset((page - 1) * page_size).limit(page_size).all()
        result: list[dict[str, Any]] = []
        seen_students: set[str] = set()
        for _class_student, student, score in rows:
            if student.id in seen_students:
                continue
            seen_students.add(student.id)
            result.append({
                'id': score.id if score else f'external-readonly:{student.id}',
                'class_id': class_id,
                'student_id': student.id,
                'student_code': student.student_code,
                'student_username': student.username,
                'student_name': student.full_name,
                'course_id': score.course_id if score else course_id,
                'assignment_key': score.assignment_key if score else None,
                'assignment_label': score.assignment_label if score else 'Assignment',
                'score_10': score.score_10 if score else None,
                'defense_status': score.defense_status if score else 'external_source',
                'graded_by': score.graded_by if score else None,
                'graded_at': score.graded_at if score else None,
                'note': (score.note if score else '') or 'Điểm Assignment do hệ thống khác xử lý.',
                'created_at': score.created_at if score else None,
                'updated_at': score.updated_at if score else None,
            })
        return result

    @staticmethod
    def reject_assignment_score_write() -> None:
        raise HTTPException(status_code=410, detail={
            'code': 'ASSIGNMENT_SCORE_EXTERNALIZED',
            'message': ASSIGNMENT_SCORE_EXTERNAL_MESSAGE,
        })
