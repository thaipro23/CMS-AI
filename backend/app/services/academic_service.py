from __future__ import annotations

import math
import re
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
    AcademicCourseMapping,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.business_rbac import BusinessRBACService
from app.services.openedx_student_insight import OpenEdXStudentInsightClient, normalize_username, mask_email
from app.core.config import settings


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


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {'1', 'true', 'yes', 'y', 'active'}:
        return True
    if raw in {'0', 'false', 'no', 'n', 'inactive'}:
        return False
    return bool(raw)




def _clean_token(value: Any) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '', str(value or '')).upper()


def _normalize_text_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _parse_openedx_course_id(course_id: str) -> dict[str, str] | None:
    raw = str(course_id or '').strip()
    match = re.match(r'^course-v1:([^+\s]+)\+([^+\s]+)\+([^+\s]+)$', raw)
    if not match:
        return None
    return {'org': match.group(1), 'course': match.group(2), 'run': match.group(3), 'raw': raw}


def _term_run_candidates(term: AcademicTerm | None) -> set[str]:
    if not term:
        return set()
    raw_values = {term.term_code, term.term_name}
    candidates: set[str] = set()
    for raw in raw_values:
        text = str(raw or '').strip()
        if not text:
            continue
        candidates.add(_clean_token(text))
        lower = text.lower()
        year_match = re.search(r'(20\d{2}|\d{2})', lower)
        year = year_match.group(1) if year_match else ''
        yy = year[-2:] if year else ''
        yyyy = f'20{yy}' if len(year) == 2 else year
        prefix = ''
        if any(key in lower for key in ['spring', 'sp', 'xuân']):
            prefix = 'SP'
        elif any(key in lower for key in ['summer', 'su', 'hè']):
            prefix = 'SU'
        elif any(key in lower for key in ['fall', 'fa', 'autumn', 'thu']):
            prefix = 'FA'
        if prefix and yy:
            candidates.add(f'{prefix}{yy}')
            candidates.add(f'{prefix}{yyyy}')
    return {item for item in candidates if item}


def _suggest_course_run(term: AcademicTerm | None) -> str:
    candidates = sorted(_term_run_candidates(term), key=lambda item: (len(item), item))
    for item in candidates:
        if re.match(r'^(SP|SU|FA)\d{2,4}$', item):
            return item
    return candidates[0] if candidates else 'TERM'


def _check(code: str, status_value: str, message: str, metadata: dict[str, Any] | None = None, *, blocking: bool | None = None) -> dict[str, Any]:
    if blocking is None:
        blocking = status_value == 'fail'
    return {'code': code, 'status': status_value, 'message': message, 'metadata': metadata or {}, 'blocking': bool(blocking)}


def _validation_result(checks: list[dict[str, Any]], *, suggested: str | None = None, parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    has_fail = any(item.get('status') == 'fail' for item in checks)
    has_warn = any(item.get('status') == 'warn' for item in checks)
    risk = 'high' if has_fail else ('medium' if has_warn else 'low')
    if has_fail:
        message = 'Mapping chưa an toàn. Cần sửa lỗi trước khi lưu.'
    elif has_warn:
        message = 'Mapping có cảnh báo. Có thể lưu nếu đã kiểm tra thủ công.'
    else:
        message = 'Mapping hợp lệ.'
    return {
        'ok': not has_fail,
        'can_save': not has_fail,
        'risk_level': risk,
        'message': message,
        'checks': checks,
        'suggested_openedx_course_id': suggested,
        'parsed_course': parsed,
    }

def _safe_mapping_raw(result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    safe: dict[str, Any] = {}
    for key, value in result.items():
        if key in {'email', 'openedx_email', 'ap_email'}:
            safe[key] = mask_email(value)
        elif key in {'full_name', 'name', 'phone'}:
            safe[key] = '***REDACTED***'
        else:
            safe[key] = value
    return safe


def _derive_mapping_status(result: dict[str, Any] | None) -> tuple[str, str, float, str]:
    result = result or {}
    explicit_status = str(result.get('match_status') or '').strip().lower()
    explicit_method = str(result.get('match_method') or '').strip().lower()
    exists = result.get('exists')
    is_active = result.get('is_active')
    note = str(result.get('note') or result.get('message') or '').strip()
    if explicit_status:
        status = explicit_status
    elif exists is False:
        status = 'missing'
    elif result.get('ambiguous'):
        status = 'ambiguous'
    elif exists is True and is_active is False:
        status = 'inactive'
    elif exists is True:
        status = 'matched'
    else:
        status = 'manual_required'
    if explicit_method:
        method = explicit_method
    elif status in {'matched', 'inactive'}:
        method = 'exact_ap_username'
    elif status == 'missing':
        method = 'not_found'
    elif status == 'ambiguous':
        method = 'ambiguous'
    else:
        method = 'manual_required'
    confidence = 1.0 if status == 'matched' and method == 'exact_ap_username' else 0.0
    if status == 'inactive':
        confidence = 0.9
    if status == 'ambiguous':
        confidence = 0.5
    return status, method, confidence, note


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

    def save_term_with_blocks(self, payload: dict[str, Any]) -> AcademicTerm:
        term_code = str(payload.get('term_code') or '').strip()
        term_name = str(payload.get('term_name') or '').strip()
        branch = str(payload.get('branch') or 'poly').strip().lower()
        if not term_code:
            raise HTTPException(status_code=400, detail='Thiếu mã học kỳ')
        if not term_name:
            raise HTTPException(status_code=400, detail='Thiếu tên học kỳ')
        term_id = str(payload.get('id') or '').strip()
        query = self.db.query(AcademicTerm)
        term = query.filter(AcademicTerm.id == term_id).first() if term_id else None
        if not term:
            term = self.db.query(AcademicTerm).filter(AcademicTerm.term_code == term_code, AcademicTerm.branch == branch).first()
        if not term:
            term = AcademicTerm(term_code=term_code, term_name=term_name, branch=branch)
            self.db.add(term)
        term.ap_term_id = str(payload.get('ap_term_id') or '').strip() or term.ap_term_id
        term.term_code = term_code
        term.term_name = term_name
        term.branch = branch
        term.start_date = payload.get('start_date')
        term.end_date = payload.get('end_date')
        term.active = _boolish(payload.get('active')) is not False
        meta = dict(term.metadata_json or {})
        meta.update({'source': meta.get('source') or 'manual_ui', 'updated_from': 'terms_page'})
        term.metadata_json = meta
        self.db.flush()

        seen_block_ids: set[str] = set()
        for index, raw_block in enumerate(payload.get('blocks') or [], start=1):
            block_code = str(raw_block.get('block_code') or raw_block.get('block_name') or f'Block {index}').strip()
            block_name = str(raw_block.get('block_name') or block_code).strip()
            block_id = str(raw_block.get('id') or '').strip()
            block = self.db.query(AcademicBlock).filter(AcademicBlock.id == block_id, AcademicBlock.term_id == term.id).first() if block_id else None
            if not block:
                block = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id, AcademicBlock.block_code == block_code).first()
            if not block:
                block = AcademicBlock(term_id=term.id, block_code=block_code, block_name=block_name)
                self.db.add(block)
            block.ap_block_id = str(raw_block.get('ap_block_id') or '').strip() or block.ap_block_id
            block.block_code = block_code
            block.block_name = block_name
            block.start_date = raw_block.get('start_date')
            block.end_date = raw_block.get('end_date')
            block.sort_order = int(raw_block.get('sort_order') or index)
            block.active = _boolish(raw_block.get('active')) is not False
            block_meta = dict(block.metadata_json or {})
            block_meta.update({'source': block_meta.get('source') or 'manual_ui', 'updated_from': 'terms_page'})
            block.metadata_json = block_meta
            self.db.flush()
            seen_block_ids.add(block.id)

        # Do not hard-delete old blocks; hide blocks removed from the popup so historical classes stay valid.
        if payload.get('blocks'):
            old_blocks = self.db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id).all()
            for block in old_blocks:
                if block.id not in seen_block_ids:
                    block.active = False

        self.db.commit()
        self.db.refresh(term)
        return term

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

        # PostgreSQL requires SELECT DISTINCT ON columns to be the first ORDER BY columns.
        # The previous implementation joined teacher assignments directly, then used
        # query.distinct(AcademicClass.id, AcademicTeacher.id) with a business ORDER BY,
        # which fails in production. Aggregate teacher display fields per class instead
        # so the main query remains one row per class and can be sorted naturally.
        teacher_summary_sq = self.db.query(
            AcademicTeacherAssignment.class_id.label('class_id'),
            func.min(AcademicTeacher.username).label('teacher_username'),
            func.min(AcademicTeacher.full_name).label('teacher_name'),
        ).join(AcademicTeacher, AcademicTeacher.id == AcademicTeacherAssignment.teacher_id)
        teacher_summary_sq = teacher_summary_sq.group_by(AcademicTeacherAssignment.class_id).subquery()

        query = self.db.query(
            AcademicClass,
            AcademicTerm.term_name,
            AcademicBlock.block_name,
            AcademicSubject.subject_code,
            AcademicSubject.subject_name,
            teacher_summary_sq.c.teacher_username.label('teacher_username'),
            teacher_summary_sq.c.teacher_name.label('teacher_name'),
            func.coalesce(student_count_sq.c.student_count, 0).label('student_count'),
            AcademicClassCourseMapping.openedx_course_id,
            AcademicClassCourseMapping.openedx_cohort_name,
        ).join(AcademicTerm, AcademicTerm.id == AcademicClass.term_id)
        query = query.outerjoin(AcademicBlock, AcademicBlock.id == AcademicClass.block_id)
        query = query.join(AcademicSubject, AcademicSubject.id == AcademicClass.subject_id)
        query = query.outerjoin(teacher_summary_sq, teacher_summary_sq.c.class_id == AcademicClass.id)
        query = query.outerjoin(student_count_sq, student_count_sq.c.class_id == AcademicClass.id)
        query = query.outerjoin(
            AcademicClassCourseMapping,
            and_(AcademicClassCourseMapping.class_id == AcademicClass.id, AcademicClassCourseMapping.active.is_(True)),
        )
        if not decision.unrestricted:
            if not decision.teacher_ids:
                return {'items': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0, 'has_next': False}
            allowed_class_ids = self.db.query(AcademicTeacherAssignment.class_id).filter(
                AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids)
            )
            query = query.filter(AcademicClass.id.in_(allowed_class_ids))
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if block_id:
            query = query.filter(AcademicClass.block_id == block_id)
        if subject_id:
            query = query.filter(AcademicClass.subject_id == subject_id)
        if search and search.strip():
            like = f"%{search.strip()}%"
            teacher_match_class_ids = self.db.query(AcademicTeacherAssignment.class_id).join(
                AcademicTeacher, AcademicTeacher.id == AcademicTeacherAssignment.teacher_id
            ).filter(or_(AcademicTeacher.username.ilike(like), AcademicTeacher.full_name.ilike(like)))
            query = query.filter(or_(
                AcademicClass.class_code.ilike(like),
                AcademicClass.class_name.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
                AcademicClass.id.in_(teacher_match_class_ids),
            ))
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
                'openedx_mapping_source': 'class_override' if row.openedx_course_id else None,
                'openedx_mapping_validation_status': None,
            })
        for entry in items:
            if entry.get('openedx_course_id'):
                continue
            cls_for_mapping = self.db.get(AcademicClass, entry['id'])
            inherited = self.inherited_course_mapping_for_class(cls_for_mapping) if cls_for_mapping else None
            if inherited:
                entry['openedx_course_id'] = inherited.openedx_course_id
                entry['openedx_cohort_name'] = entry['class_code']
                entry['openedx_mapping_source'] = 'subject_term_mapping'
                entry['openedx_mapping_validation_status'] = inherited.validation_status
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
            'openedx_course_id': mapping.openedx_course_id if mapping else (self.inherited_course_mapping_for_class(cls).openedx_course_id if self.inherited_course_mapping_for_class(cls) else None),
            'openedx_cohort_name': mapping.openedx_cohort_name if mapping else (cls.class_code if self.inherited_course_mapping_for_class(cls) else None),
            'openedx_mapping_source': 'class_override' if mapping else ('subject_term_mapping' if self.inherited_course_mapping_for_class(cls) else None),
            'openedx_mapping_validation_status': mapping.validation_status if mapping else (self.inherited_course_mapping_for_class(cls).validation_status if self.inherited_course_mapping_for_class(cls) else None),
        }

    def _student_mapping_item(self, class_id: str, student: AcademicStudent, synced_at: datetime | None, mapping: OpenEdXUserMapping | None) -> dict[str, Any]:
        return {
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
            'mapping_id': mapping.id if mapping else None,
            'openedx_user_id': mapping.openedx_user_id if mapping else None,
            'openedx_username': mapping.openedx_username if mapping else None,
            'openedx_email': mapping.openedx_email if mapping else None,
            'openedx_is_active': mapping.openedx_is_active if mapping else None,
            'match_status': mapping.match_status if mapping else 'not_checked',
            'match_method': mapping.match_method if mapping else 'not_checked',
            'mapping_confidence': mapping.confidence if mapping else 0.0,
            'mapping_note': mapping.note if mapping else '',
            'last_resolved_at': mapping.last_resolved_at if mapping else None,
        }

    def list_class_students(self, user: UserContext, class_id: str, *, search: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        page, page_size = _page(page, page_size)
        query = self.db.query(AcademicStudent, AcademicClassStudent.synced_at, OpenEdXUserMapping).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(
            OpenEdXUserMapping,
            OpenEdXUserMapping.student_id == AcademicStudent.id,
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
        total = query.count()
        rows = query.order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).offset((page - 1) * page_size).limit(page_size).all()
        items = [self._student_mapping_item(class_id, student, synced_at, mapping) for student, synced_at, mapping in rows]
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}
    def _upsert_mapping(self, student: AcademicStudent, result: dict[str, Any] | None, *, source: str = 'plugin') -> OpenEdXUserMapping:
        now = datetime.utcnow()
        result = result or {}
        status_value, method_value, confidence, note = _derive_mapping_status(result)
        mapping = self.db.query(OpenEdXUserMapping).filter(OpenEdXUserMapping.student_id == student.id).first()
        if not mapping:
            mapping = OpenEdXUserMapping(
                student_id=student.id,
                ap_username=normalize_username(student.username),
                ap_student_code=student.student_code,
                ap_email=student.email,
                created_at=now,
            )
        mapping.ap_username = normalize_username(student.username)
        mapping.ap_student_code = student.student_code
        mapping.ap_email = student.email
        mapping.openedx_user_id = str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None
        mapping.openedx_username = str(result.get('openedx_username') or result.get('username') or '').strip() or None
        mapping.openedx_email = str(result.get('openedx_email') or result.get('email') or '').strip() or None
        if 'is_active' in result:
            mapping.openedx_is_active = _boolish(result.get('is_active'))
        elif 'openedx_is_active' in result:
            mapping.openedx_is_active = _boolish(result.get('openedx_is_active'))
        elif status_value == 'missing':
            mapping.openedx_is_active = None
        mapping.match_status = status_value
        mapping.match_method = method_value
        mapping.confidence = confidence
        mapping.note = note[:4000]
        mapping.raw_json = {'source': source, 'payload': _safe_mapping_raw(result)}
        mapping.last_resolved_at = now
        mapping.updated_at = now
        self.db.add(mapping)
        return mapping


    def _scope_filter_course_mapping(self, *, term_id: str, block_id: str | None, subject_id: str, campus: str | None, branch: str | None):
        query = self.db.query(AcademicCourseMapping).filter(
            AcademicCourseMapping.term_id == term_id,
            AcademicCourseMapping.subject_id == subject_id,
            AcademicCourseMapping.active.is_(True),
        )
        query = query.filter(AcademicCourseMapping.block_id.is_(None) if block_id is None else AcademicCourseMapping.block_id == block_id)
        query = query.filter(AcademicCourseMapping.campus.is_(None) if campus is None else AcademicCourseMapping.campus == campus)
        query = query.filter(AcademicCourseMapping.branch.is_(None) if branch is None else AcademicCourseMapping.branch == branch)
        return query

    def _course_mapping_item(self, mapping: AcademicCourseMapping) -> dict[str, Any]:
        term = self.db.get(AcademicTerm, mapping.term_id)
        block = self.db.get(AcademicBlock, mapping.block_id) if mapping.block_id else None
        subject = self.db.get(AcademicSubject, mapping.subject_id)
        return {
            'id': mapping.id,
            'term_id': mapping.term_id,
            'term_name': term.term_name if term else None,
            'block_id': mapping.block_id,
            'block_name': block.block_name if block else None,
            'subject_id': mapping.subject_id,
            'subject_code': subject.subject_code if subject else None,
            'subject_name': subject.subject_name if subject else None,
            'campus': mapping.campus,
            'branch': mapping.branch,
            'openedx_course_id': mapping.openedx_course_id,
            'openedx_course_title': mapping.openedx_course_title,
            'validation_status': mapping.validation_status,
            'validation_json': mapping.validation_json,
            'validated_at': mapping.validated_at,
            'note': mapping.note,
            'active': mapping.active,
            'created_by': mapping.created_by,
            'updated_by': mapping.updated_by,
            'created_at': mapping.created_at,
            'updated_at': mapping.updated_at,
        }

    def _class_course_mapping_item(self, mapping: AcademicClassCourseMapping) -> dict[str, Any]:
        cls = self.db.get(AcademicClass, mapping.class_id)
        term = self.db.get(AcademicTerm, cls.term_id) if cls else None
        block = self.db.get(AcademicBlock, cls.block_id) if cls and cls.block_id else None
        subject = self.db.get(AcademicSubject, cls.subject_id) if cls else None
        return {
            'id': mapping.id,
            'class_id': mapping.class_id,
            'class_code': cls.class_code if cls else None,
            'term_id': cls.term_id if cls else None,
            'term_name': term.term_name if term else None,
            'block_id': cls.block_id if cls else None,
            'block_name': block.block_name if block else None,
            'subject_id': cls.subject_id if cls else None,
            'subject_code': subject.subject_code if subject else None,
            'openedx_course_id': mapping.openedx_course_id,
            'openedx_cohort_name': mapping.openedx_cohort_name,
            'openedx_course_title': mapping.openedx_course_title,
            'mapping_source': mapping.mapping_source,
            'validation_status': mapping.validation_status,
            'validation_json': mapping.validation_json,
            'validated_at': mapping.validated_at,
            'note': mapping.note,
            'active': mapping.active,
            'created_by': mapping.created_by,
            'updated_by': mapping.updated_by,
            'created_at': mapping.created_at,
            'updated_at': mapping.updated_at,
        }

    def list_course_mappings(
        self,
        user: UserContext,
        *,
        term_id: str | None = None,
        block_id: str | None = None,
        subject_id: str | None = None,
        search: str | None = None,
        active: bool | None = True,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        if not self.rbac.is_system_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Chỉ admin được xem/sửa cấu hình map course AP ↔ Open edX')
        page, page_size = _page(page, page_size)
        query = self.db.query(AcademicCourseMapping)
        if active is not None:
            query = query.filter(AcademicCourseMapping.active.is_(active))
        if term_id:
            query = query.filter(AcademicCourseMapping.term_id == term_id)
        if block_id:
            query = query.filter(AcademicCourseMapping.block_id == block_id)
        if subject_id:
            query = query.filter(AcademicCourseMapping.subject_id == subject_id)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.outerjoin(AcademicSubject, AcademicSubject.id == AcademicCourseMapping.subject_id).filter(or_(
                AcademicCourseMapping.openedx_course_id.ilike(like),
                AcademicCourseMapping.openedx_course_title.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
            ))
        total = query.count()
        rows = query.order_by(AcademicCourseMapping.updated_at.desc(), AcademicCourseMapping.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': [self._course_mapping_item(item) for item in rows], 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}

    def suggested_course_id_for_scope(self, term_id: str, subject_id: str, *, org: str = 'FPT') -> str:
        term = self.db.get(AcademicTerm, term_id)
        subject = self.db.get(AcademicSubject, subject_id)
        if not term or not subject:
            return f'course-v1:{org}+SUBJECT+TERM'
        return f'course-v1:{org}+{_clean_token(subject.subject_code)}+{_suggest_course_run(term)}'

    def validate_course_mapping_payload(self, *, term_id: str, subject_id: str, openedx_course_id: str, block_id: str | None = None, campus: str | None = None, branch: str | None = None, openedx_course_title: str | None = None, class_id: str | None = None, cohort_name: str | None = None) -> dict[str, Any]:
        term = self.db.get(AcademicTerm, term_id)
        block = self.db.get(AcademicBlock, block_id) if block_id else None
        subject = self.db.get(AcademicSubject, subject_id)
        checks: list[dict[str, Any]] = []
        if not term:
            checks.append(_check('term_exists', 'fail', 'Không tìm thấy kỳ AP.'))
        if block_id and not block:
            checks.append(_check('block_exists', 'fail', 'Không tìm thấy block AP.'))
        if not subject:
            checks.append(_check('subject_exists', 'fail', 'Không tìm thấy môn AP.'))
        suggested = self.suggested_course_id_for_scope(term_id, subject_id)
        parsed = _parse_openedx_course_id(openedx_course_id)
        if not parsed:
            checks.append(_check('course_id_format', 'fail', 'Course ID phải đúng dạng course-v1:ORG+COURSE+RUN.'))
            return _validation_result(checks, suggested=suggested, parsed=None)
        checks.append(_check('course_id_format', 'pass', 'Course ID đúng định dạng Open edX.', parsed, blocking=False))
        if subject:
            if _normalize_text_key(parsed['course']) == _normalize_text_key(subject.subject_code):
                checks.append(_check('subject_match', 'pass', f'Course part {parsed["course"]} khớp mã môn {subject.subject_code}.', blocking=False))
            else:
                checks.append(_check('subject_match', 'fail', f'Course part {parsed["course"]} không khớp mã môn AP {subject.subject_code}.'))
        candidates = _term_run_candidates(term)
        if candidates and _clean_token(parsed['run']) in candidates:
            checks.append(_check('term_match', 'pass', f'Course run {parsed["run"]} khớp kỳ AP.', {'candidates': sorted(candidates)}, blocking=False))
        elif candidates:
            checks.append(_check('term_match', 'warn', f'Course run {parsed["run"]} chưa khớp kỳ AP. Cần kiểm tra tránh map nhầm kỳ.', {'candidates': sorted(candidates)}, blocking=False))
        if class_id and cohort_name:
            cls = self.db.get(AcademicClass, class_id)
            if cls and _normalize_text_key(cohort_name) == _normalize_text_key(cls.class_code):
                checks.append(_check('cohort_match', 'pass', 'Cohort khớp mã lớp AP.', blocking=False))
            elif cls:
                checks.append(_check('cohort_match', 'warn', f'Cohort {cohort_name} khác mã lớp AP {cls.class_code}. Nếu Open edX đặt cohort khác, vẫn có thể lưu.', blocking=False))
        duplicate_course = self.db.query(AcademicCourseMapping).filter(
            AcademicCourseMapping.openedx_course_id == parsed['raw'],
            AcademicCourseMapping.active.is_(True),
        ).first()
        if duplicate_course and (duplicate_course.term_id != term_id or duplicate_course.subject_id != subject_id or duplicate_course.block_id != block_id):
            checks.append(_check('duplicate_subject_mapping', 'warn', 'Course này đã có mapping cấp môn/kỳ/block khác. Kiểm tra trước khi lưu.', {'mapping_id': duplicate_course.id}, blocking=False))
        duplicate_class = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.openedx_course_id == parsed['raw'],
            AcademicClassCourseMapping.active.is_(True),
        ).first()
        if duplicate_class and duplicate_class.class_id != class_id:
            checks.append(_check('duplicate_class_mapping', 'warn', 'Course này đã được map trực tiếp cho lớp khác. Nếu nhiều lớp cùng học chung course thì vẫn hợp lệ.', {'mapping_id': duplicate_class.id, 'class_id': duplicate_class.class_id}, blocking=False))
        checks.append(_check('openedx_live_validation', 'warn', 'Chưa validate live course structure. Bản sau sẽ dùng LMS Student Insight/CMS connector để kiểm tra course/cohort thật.', blocking=False))
        if openedx_course_title and subject:
            left = _normalize_text_key(openedx_course_title)
            right = _normalize_text_key(subject.subject_name)
            if left and right and (left in right or right in left):
                checks.append(_check('course_title_similarity', 'pass', 'Tên course có vẻ khớp tên môn.', blocking=False))
            else:
                checks.append(_check('course_title_similarity', 'warn', 'Tên course khác tên môn AP. Cần kiểm tra thủ công.', blocking=False))
        return _validation_result(checks, suggested=suggested, parsed=parsed)

    def create_or_update_course_mapping(self, user: UserContext, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.rbac.is_system_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Chỉ admin được tạo mapping course AP ↔ Open edX')
        validation = self.validate_course_mapping_payload(**{k: payload.get(k) for k in ['term_id', 'subject_id', 'openedx_course_id', 'block_id', 'campus', 'branch', 'openedx_course_title']})
        if not validation['can_save']:
            raise HTTPException(status_code=400, detail=validation['message'])
        if validation['risk_level'] == 'medium' and not payload.get('allow_warnings'):
            raise HTTPException(status_code=400, detail='Mapping có cảnh báo. Kiểm tra lại hoặc bật allow_warnings=true nếu vẫn muốn lưu.')
        now = datetime.utcnow()
        mapping = self._scope_filter_course_mapping(
            term_id=payload['term_id'],
            block_id=payload.get('block_id'),
            subject_id=payload['subject_id'],
            campus=payload.get('campus'),
            branch=payload.get('branch'),
        ).first()
        if not mapping:
            mapping = AcademicCourseMapping(
                term_id=payload['term_id'],
                block_id=payload.get('block_id'),
                subject_id=payload['subject_id'],
                campus=payload.get('campus'),
                branch=payload.get('branch'),
                created_by=user.user_id,
                created_at=now,
            )
        mapping.openedx_course_id = str(payload.get('openedx_course_id') or '').strip()
        mapping.openedx_course_title = str(payload.get('openedx_course_title') or '').strip() or None
        mapping.validation_status = validation['risk_level']
        mapping.validation_json = validation
        mapping.validated_at = now
        mapping.updated_by = user.user_id
        mapping.note = str(payload.get('note') or '').strip()[:4000]
        mapping.active = True
        mapping.updated_at = now
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return self._course_mapping_item(mapping)

    def deactivate_course_mapping(self, user: UserContext, mapping_id: str) -> dict[str, Any]:
        if not self.rbac.is_system_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Chỉ admin được tắt mapping course')
        mapping = self.db.get(AcademicCourseMapping, mapping_id)
        if not mapping:
            raise HTTPException(status_code=404, detail='Không tìm thấy mapping course')
        mapping.active = False
        mapping.updated_by = user.user_id
        mapping.updated_at = datetime.utcnow()
        self.db.add(mapping)
        self.db.commit()
        return self._course_mapping_item(mapping)

    def inherited_course_mapping_for_class(self, cls: AcademicClass) -> AcademicCourseMapping | None:
        # Prefer exact block mapping, then term+subject mapping without block.
        filters = [
            (cls.block_id, cls.campus, cls.branch),
            (cls.block_id, None, cls.branch),
            (cls.block_id, cls.campus, None),
            (cls.block_id, None, None),
            (None, cls.campus, cls.branch),
            (None, None, cls.branch),
            (None, cls.campus, None),
            (None, None, None),
        ]
        for block_id, campus, branch in filters:
            found = self._scope_filter_course_mapping(term_id=cls.term_id, block_id=block_id, subject_id=cls.subject_id, campus=campus, branch=branch).first()
            if found:
                return found
        return None

    def class_course_mapping_proposal(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        subject = self.db.get(AcademicSubject, cls.subject_id)
        suggested = self.suggested_course_id_for_scope(cls.term_id, cls.subject_id)
        class_mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == class_id, AcademicClassCourseMapping.active.is_(True)).first()
        inherited = self.inherited_course_mapping_for_class(cls)
        effective_course_id = class_mapping.openedx_course_id if class_mapping else (inherited.openedx_course_id if inherited else None)
        effective_cohort = class_mapping.openedx_cohort_name if class_mapping else cls.class_code
        source = 'class_override' if class_mapping else ('subject_term_mapping' if inherited else 'proposal_only')
        return {
            'class_id': class_id,
            'class_code': cls.class_code,
            'suggested_openedx_course_id': inherited.openedx_course_id if inherited else suggested,
            'suggested_cohort_name': cls.class_code,
            'inherited_course_mapping': self._course_mapping_item(inherited) if inherited else None,
            'effective_openedx_course_id': effective_course_id,
            'effective_openedx_cohort_name': effective_cohort,
            'effective_mapping_source': source,
            'checks': [
                _check('class_exists', 'pass', 'Đã tìm thấy lớp AP.', blocking=False),
                _check('subject_code', 'pass' if subject else 'fail', f'Môn AP: {subject.subject_code if subject else "không tìm thấy"}', blocking=not bool(subject)),
            ],
        }

    def validate_class_course_mapping(self, user: UserContext, class_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        return self.validate_course_mapping_payload(
            term_id=cls.term_id,
            block_id=cls.block_id,
            subject_id=cls.subject_id,
            campus=cls.campus,
            branch=cls.branch,
            openedx_course_id=payload.get('openedx_course_id'),
            openedx_course_title=payload.get('openedx_course_title'),
            class_id=class_id,
            cohort_name=payload.get('openedx_cohort_name'),
        )

    def create_or_update_class_course_mapping(self, user: UserContext, class_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        validation = self.validate_class_course_mapping(user, class_id, payload)
        if not validation['can_save']:
            raise HTTPException(status_code=400, detail=validation['message'])
        if validation['risk_level'] == 'medium' and not payload.get('allow_warnings'):
            raise HTTPException(status_code=400, detail='Mapping có cảnh báo. Kiểm tra lại hoặc bật allow_warnings=true nếu vẫn muốn lưu.')
        now = datetime.utcnow()
        mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == class_id).first()
        if not mapping:
            mapping = AcademicClassCourseMapping(class_id=class_id, created_by=user.user_id, created_at=now)
        mapping.openedx_course_id = str(payload.get('openedx_course_id') or '').strip()
        mapping.openedx_cohort_name = str(payload.get('openedx_cohort_name') or '').strip() or None
        mapping.openedx_course_title = str(payload.get('openedx_course_title') or '').strip() or None
        mapping.mapping_source = 'class_override'
        mapping.validation_status = validation['risk_level']
        mapping.validation_json = validation
        mapping.validated_at = now
        mapping.updated_by = user.user_id
        mapping.note = str(payload.get('note') or '').strip()[:4000]
        mapping.active = True
        mapping.updated_at = now
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return self._class_course_mapping_item(mapping)

    def deactivate_class_course_mapping(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == class_id, AcademicClassCourseMapping.active.is_(True)).first()
        if not mapping:
            raise HTTPException(status_code=404, detail='Lớp này chưa có mapping course riêng')
        mapping.active = False
        mapping.updated_by = user.user_id
        mapping.updated_at = datetime.utcnow()
        self.db.add(mapping)
        self.db.commit()
        return self._class_course_mapping_item(mapping)

    def mapping_summary_for_class(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        rows = self.db.query(OpenEdXUserMapping.match_status, func.count(AcademicClassStudent.id)).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == OpenEdXUserMapping.student_id,
        ).filter(AcademicClassStudent.class_id == class_id).group_by(OpenEdXUserMapping.match_status).all()
        total = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == class_id).scalar() or 0
        counts = {str(status or 'not_checked'): int(count or 0) for status, count in rows}
        checked = sum(counts.values())
        counts['not_checked'] = max(0, int(total) - checked) + counts.get('not_checked', 0)
        return {'class_id': class_id, 'total': int(total), 'counts': counts}

    def resolve_class_openedx_users(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        limit = max(1, min(5000, int(limit or 1000)))
        query = self.db.query(AcademicStudent, OpenEdXUserMapping).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id == class_id,
        ).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = query.all()
        if not force:
            rows = [(student, mapping) for student, mapping in rows if not mapping or mapping.match_status not in {'matched'}]
        if not rows:
            return {'ok': True, 'class_id': class_id, 'total': 0, 'updated': 0, 'counts': {}, 'message': 'Không có sinh viên cần resolve'}

        client = OpenEdXStudentInsightClient()
        batch_size = max(1, min(settings.openedx_student_insight_max_batch_size, 100))
        updated = 0
        counts: dict[str, int] = {}
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = [{
                'student_code': student.student_code,
                'username': normalize_username(student.username),
                'email': student.email,
                'full_name': student.full_name,
            } for student, _mapping in chunk]
            results = client.resolve_users(payload)
            result_by_username = {normalize_username(item.get('ap_username') or item.get('username')): item for item in results if normalize_username(item.get('ap_username') or item.get('username'))}
            result_by_code = {str(item.get('student_code') or '').strip().lower(): item for item in results if str(item.get('student_code') or '').strip()}
            for student, _mapping in chunk:
                result = result_by_username.get(normalize_username(student.username))
                if result is None and student.student_code:
                    result = result_by_code.get(str(student.student_code).strip().lower())
                if result is None:
                    result = {
                        'student_code': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'exists': False,
                        'match_status': 'missing',
                        'match_method': 'not_found',
                        'note': 'Open edX plugin không trả user cho username AP này',
                    }
                mapping = self._upsert_mapping(student, result, source='openedx_student_insight')
                counts[mapping.match_status] = counts.get(mapping.match_status, 0) + 1
                updated += 1
            self.db.flush()
        self.db.commit()
        return {'ok': True, 'class_id': class_id, 'total': len(rows), 'updated': updated, 'counts': counts, 'message': 'Đã resolve mapping Open edX theo AP username'}

    def import_openedx_user_mappings(self, records: list[dict[str, Any]], *, requested_by: str | None = None) -> dict[str, Any]:
        now = datetime.utcnow()
        total = len(records)
        counters = {'matched': 0, 'inactive': 0, 'missing_student': 0, 'invalid': 0, 'updated': 0}
        errors: list[dict[str, Any]] = []
        for index, record in enumerate(records, start=1):
            ap_username = normalize_username(record.get('ap_username') or record.get('username') or record.get('apUserName'))
            student_code = str(record.get('student_code') or record.get('studentCode') or record.get('ap_student_code') or '').strip()
            if not ap_username and not student_code:
                counters['invalid'] += 1
                errors.append({'row': index, 'message': 'Thiếu ap_username hoặc student_code'})
                continue
            student_query = self.db.query(AcademicStudent)
            if ap_username:
                student = student_query.filter(func.lower(AcademicStudent.username) == ap_username).first()
            else:
                student = None
            if not student and student_code:
                student = self.db.query(AcademicStudent).filter(func.lower(AcademicStudent.student_code) == student_code.lower()).first()
            if not student:
                counters['missing_student'] += 1
                errors.append({'row': index, 'ap_username': ap_username, 'student_code': student_code, 'message': 'Không tìm thấy sinh viên AP trong AI Server'})
                continue
            openedx_username = str(record.get('openedx_username') or record.get('openedxUsername') or record.get('username') or '').strip()
            openedx_user_id = str(record.get('openedx_user_id') or record.get('user_id') or record.get('id') or '').strip()
            is_active_raw = record.get('is_active', record.get('openedx_is_active', True))
            is_active = _boolish(is_active_raw)
            status_value = 'matched' if openedx_username or openedx_user_id else 'manual_required'
            if status_value == 'matched' and is_active is False:
                status_value = 'inactive'
            result = {
                'openedx_user_id': openedx_user_id or None,
                'openedx_username': openedx_username or normalize_username(student.username),
                'openedx_email': record.get('openedx_email') or record.get('email'),
                'is_active': True if is_active is None else is_active,
                'match_status': status_value,
                'match_method': 'manual',
                'note': str(record.get('note') or f'Imported by {requested_by or "system"} at {now.isoformat()}')[:4000],
            }
            mapping = self._upsert_mapping(student, result, source='manual_import')
            counters[mapping.match_status] = counters.get(mapping.match_status, 0) + 1
            counters['updated'] += 1
        self.db.commit()
        return {'ok': True, 'total': total, 'counters': counters, 'errors': errors[:100]}

