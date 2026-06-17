from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassCourseMapping,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.services.business_rbac import BusinessRBACService


def _actor_names(user: UserContext) -> set[str]:
    raw = user.raw_claims or {}
    values = {
        user.user_id,
        user.username,
        user.email,
        raw.get('username'),
        raw.get('preferred_username'),
        raw.get('email'),
    }
    return {str(item).strip().lower() for item in values if str(item or '').strip()}


def _page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 50)))
    return page, page_size


@dataclass(frozen=True)
class AccessDecision:
    unrestricted: bool
    teacher_ids: set[str]


class AcademicService:
    def __init__(self, db: Session):
        self.db = db
        self.rbac = BusinessRBACService(db)

    def access_decision(self, user: UserContext) -> AccessDecision:
        if self.rbac.is_system_admin(user):
            return AccessDecision(unrestricted=True, teacher_ids=set())
        names = _actor_names(user)
        if not names:
            return AccessDecision(unrestricted=False, teacher_ids=set())
        teachers = self.db.query(AcademicTeacher).filter(func.lower(AcademicTeacher.username).in_(names)).all()
        return AccessDecision(unrestricted=False, teacher_ids={item.id for item in teachers})

    def assert_can_access_class(self, user: UserContext, class_id: str) -> None:
        decision = self.access_decision(user)
        if decision.unrestricted:
            return
        if not decision.teacher_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn chưa được AP phân công lớp nào trên AI Server')
        exists = self.db.query(AcademicTeacherAssignment.id).filter(
            AcademicTeacherAssignment.class_id == class_id,
            AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids),
        ).first()
        if not exists:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không được AP phân công lớp này')

    def list_terms(self, branch: str | None = None, active: bool | None = True) -> list[AcademicTerm]:
        query = self.db.query(AcademicTerm)
        if branch:
            query = query.filter(AcademicTerm.branch == branch.strip().lower())
        if active is not None:
            query = query.filter(AcademicTerm.active.is_(active))
        return query.order_by(AcademicTerm.start_date.desc().nullslast(), AcademicTerm.term_name.desc()).all()

    def list_blocks(self, term_id: str, active: bool | None = True) -> list[AcademicBlock]:
        query = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term_id)
        if active is not None:
            query = query.filter(AcademicBlock.active.is_(active))
        return query.order_by(AcademicBlock.sort_order.asc(), AcademicBlock.block_name.asc()).all()

    def list_subjects(self, term_id: str | None = None, block_id: str | None = None, search: str | None = None, branch: str | None = None) -> list[AcademicSubject]:
        query = self.db.query(AcademicSubject)
        if term_id or block_id:
            query = query.join(AcademicClass, AcademicClass.subject_id == AcademicSubject.id)
            if term_id:
                query = query.filter(AcademicClass.term_id == term_id)
            if block_id:
                query = query.filter(AcademicClass.block_id == block_id)
        if branch:
            query = query.filter(AcademicSubject.branch == branch.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))
        return query.distinct().order_by(AcademicSubject.subject_code.asc()).limit(500).all()

    def list_teacher_classes(
        self,
        user: UserContext,
        *,
        term_id: str | None = None,
        block_id: str | None = None,
        subject_id: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        page, page_size = _page(page, page_size)
        decision = self.access_decision(user)
        student_count_sq = self.db.query(
            AcademicClassStudent.class_id.label('class_id'),
            func.count(AcademicClassStudent.student_id).label('student_count'),
        ).group_by(AcademicClassStudent.class_id).subquery()

        query = self.db.query(
            AcademicClass,
            AcademicTerm.term_name,
            AcademicBlock.block_name,
            AcademicSubject.subject_code,
            AcademicSubject.subject_name,
            AcademicTeacher.username.label('teacher_username'),
            AcademicTeacher.full_name.label('teacher_name'),
            func.coalesce(student_count_sq.c.student_count, 0).label('student_count'),
            AcademicClassCourseMapping.openedx_course_id,
            AcademicClassCourseMapping.openedx_cohort_name,
        ).join(AcademicTerm, AcademicTerm.id == AcademicClass.term_id)
        query = query.outerjoin(AcademicBlock, AcademicBlock.id == AcademicClass.block_id)
        query = query.join(AcademicSubject, AcademicSubject.id == AcademicClass.subject_id)
        query = query.join(AcademicTeacherAssignment, AcademicTeacherAssignment.class_id == AcademicClass.id)
        query = query.join(AcademicTeacher, AcademicTeacher.id == AcademicTeacherAssignment.teacher_id)
        query = query.outerjoin(student_count_sq, student_count_sq.c.class_id == AcademicClass.id)
        query = query.outerjoin(
            AcademicClassCourseMapping,
            and_(AcademicClassCourseMapping.class_id == AcademicClass.id, AcademicClassCourseMapping.active.is_(True)),
        )
        if not decision.unrestricted:
            if not decision.teacher_ids:
                return {'items': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0, 'has_next': False}
            query = query.filter(AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids))
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if block_id:
            query = query.filter(AcademicClass.block_id == block_id)
        if subject_id:
            query = query.filter(AcademicClass.subject_id == subject_id)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicClass.class_code.ilike(like),
                AcademicClass.class_name.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
                AcademicTeacher.username.ilike(like),
            ))
        query = query.distinct(AcademicClass.id, AcademicTeacher.id) if self.db.bind and self.db.bind.dialect.name == 'postgresql' else query
        total = query.count()
        rows = query.order_by(AcademicTerm.start_date.desc().nullslast(), AcademicBlock.sort_order.asc().nullslast(), AcademicSubject.subject_code.asc(), AcademicClass.class_code.asc()).offset((page - 1) * page_size).limit(page_size).all()
        items = []
        seen: set[str] = set()
        for row in rows:
            item = row[0]
            # When a class has multiple teachers, keep the first row in this light DTO.
            if item.id in seen:
                continue
            seen.add(item.id)
            items.append({
                'id': item.id,
                'ap_class_id': item.ap_class_id,
                'term_id': item.term_id,
                'term_name': row.term_name,
                'block_id': item.block_id,
                'block_name': row.block_name,
                'subject_id': item.subject_id,
                'subject_code': row.subject_code,
                'subject_name': row.subject_name,
                'class_code': item.class_code,
                'class_name': item.class_name,
                'campus': item.campus,
                'branch': item.branch,
                'start_date': item.start_date,
                'end_date': item.end_date,
                'active': item.active,
                'teacher_username': row.teacher_username,
                'teacher_name': row.teacher_name,
                'student_count': int(row.student_count or 0),
                'openedx_course_id': row.openedx_course_id,
                'openedx_cohort_name': row.openedx_cohort_name,
            })
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}

    def get_class_detail(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        data = self.list_teacher_classes(user, search=None, page=1, page_size=1)
        # Avoid a second bespoke serializer drifting from the list contract.
        query_result = self.list_teacher_classes(user, page=1, page_size=200)
        for item in query_result['items']:
            if item['id'] == class_id:
                return item
        # Fallback for admin/detail when the class is outside first page.
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        term = self.db.get(AcademicTerm, cls.term_id)
        block = self.db.get(AcademicBlock, cls.block_id) if cls.block_id else None
        subject = self.db.get(AcademicSubject, cls.subject_id)
        mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == cls.id, AcademicClassCourseMapping.active.is_(True)).first()
        student_count = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == cls.id).scalar() or 0
        teacher = self.db.query(AcademicTeacher).join(AcademicTeacherAssignment, AcademicTeacherAssignment.teacher_id == AcademicTeacher.id).filter(AcademicTeacherAssignment.class_id == cls.id).first()
        return {
            'id': cls.id,
            'ap_class_id': cls.ap_class_id,
            'term_id': cls.term_id,
            'term_name': term.term_name if term else None,
            'block_id': cls.block_id,
            'block_name': block.block_name if block else None,
            'subject_id': cls.subject_id,
            'subject_code': subject.subject_code if subject else None,
            'subject_name': subject.subject_name if subject else None,
            'class_code': cls.class_code,
            'class_name': cls.class_name,
            'campus': cls.campus,
            'branch': cls.branch,
            'start_date': cls.start_date,
            'end_date': cls.end_date,
            'active': cls.active,
            'teacher_username': teacher.username if teacher else None,
            'teacher_name': teacher.full_name if teacher else None,
            'student_count': int(student_count),
            'openedx_course_id': mapping.openedx_course_id if mapping else None,
            'openedx_cohort_name': mapping.openedx_cohort_name if mapping else None,
        }

    def list_class_students(self, user: UserContext, class_id: str, *, search: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        page, page_size = _page(page, page_size)
        query = self.db.query(AcademicStudent, AcademicClassStudent.synced_at).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).filter(AcademicClassStudent.class_id == class_id)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicStudent.student_code.ilike(like),
                AcademicStudent.username.ilike(like),
                AcademicStudent.full_name.ilike(like),
                AcademicStudent.email.ilike(like),
            ))
        total = query.count()
        rows = query.order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).offset((page - 1) * page_size).limit(page_size).all()
        items = []
        for student, synced_at in rows:
            items.append({
                'class_id': class_id,
                'id': student.id,
                'student_code': student.student_code,
                'username': student.username,
                'email': student.email,
                'full_name': student.full_name,
                'phone': student.phone,
                'campus': student.campus,
                'branch': student.branch,
                'active': student.active,
                'synced_at': synced_at,
            })
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}
