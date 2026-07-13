from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import AcademicClass, AcademicSubject, AcademicTeacher, AcademicTeacherAssignment
from app.services.academic.helpers import AccessDecision, _actor_names


class AcademicAccessWorkflowService:
    """Student Ops access boundary for AP class/student workflows.

    This workflow intentionally keeps Student Ops separate from Quiz Bank RBAC.
    Campus ownership and AP teacher assignment can grant class/student visibility;
    Department/Subject/Reviewer roles by themselves must not grant AP roster access.
    """

    def __init__(self, db: Session, rbac: Any):
        self.db = db
        self.rbac = rbac

    def access_decision(self, user: UserContext) -> AccessDecision:
        if self.rbac.is_system_admin(user):
            return AccessDecision(unrestricted=True, teacher_ids=set(), subject_codes=set(), campus_codes=set())
        names = _actor_names(user)
        teachers = []
        if names:
            teachers = self.db.query(AcademicTeacher).filter(or_(
                func.lower(AcademicTeacher.username).in_(names),
                func.lower(AcademicTeacher.email).in_(names),
            )).all()

        # Student Ops visibility comes only from campus-scoped roles and AP
        # teacher assignments. Quiz Bank roles do not grant class/student access.
        subject_codes: set[str] = set()
        campus_codes: set[str] = set()
        try:
            campus_scope = self.rbac.accessible_campus_codes(user)
            if campus_scope is None:
                return AccessDecision(unrestricted=True, teacher_ids=set(), subject_codes=set(), campus_codes=set())
            campus_codes = set(campus_scope or set())
        except Exception:
            campus_codes = set()
        return AccessDecision(
            unrestricted=False,
            teacher_ids={item.id for item in teachers},
            subject_codes=subject_codes,
            campus_codes=campus_codes,
        )

    def assert_can_access_class(self, user: UserContext, class_id: str) -> None:
        decision = self.access_decision(user)
        if decision.unrestricted:
            return
        if not decision.teacher_ids and not decision.subject_codes and not decision.campus_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Bạn chưa được phân quyền cơ sở/môn hoặc AP phân công lớp nào trên AI Server',
            )
        exists = None
        if decision.teacher_ids:
            exists = self.db.query(AcademicTeacherAssignment.id).filter(
                AcademicTeacherAssignment.class_id == class_id,
                AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids),
            ).first()
        if exists:
            return
        if decision.subject_codes:
            subject_exists = self.db.query(AcademicClass.id).join(
                AcademicSubject, AcademicSubject.id == AcademicClass.subject_id,
            ).filter(
                AcademicClass.id == class_id,
                func.lower(AcademicSubject.subject_code).in_(decision.subject_codes),
            ).first()
            if subject_exists:
                return
        if decision.campus_codes:
            campus_exists = self.db.query(AcademicClass.id).filter(
                AcademicClass.id == class_id,
                func.lower(AcademicClass.campus).in_(decision.campus_codes),
            ).first()
            if campus_exists:
                return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không được phân công hoặc phân quyền xem lớp này')

    def assert_can_access_subject(self, user: UserContext, subject_id: str) -> None:
        decision = self.access_decision(user)
        if decision.unrestricted:
            return
        subject = self.db.get(AcademicSubject, subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail='Không tìm thấy môn AP')
        if subject.subject_code and subject.subject_code.strip().lower() in decision.subject_codes:
            return
        if decision.teacher_ids:
            exists = self.db.query(AcademicTeacherAssignment.id).filter(
                AcademicTeacherAssignment.subject_id == subject_id,
                AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids),
            ).first()
            if exists:
                return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không được phân công hoặc phân quyền xem môn này')
