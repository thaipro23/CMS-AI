from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassCourseMapping,
    AcademicCourseMapping,
    AcademicClassStudent,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.business_rbac import BusinessRBACService
from app.services.openedx_student_insight import OpenEdXStudentInsightClient, normalize_username, mask_email
from app.core.config import settings
from app.models.course import CourseSyncState
from app.models.question_bank import Subject as BankSubject


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
    subject_codes: set[str]


class AcademicService:
    def __init__(self, db: Session):
        self.db = db
        self.rbac = BusinessRBACService(db)

    def access_decision(self, user: UserContext) -> AccessDecision:
        if self.rbac.is_system_admin(user):
            return AccessDecision(unrestricted=True, teacher_ids=set(), subject_codes=set())
        names = _actor_names(user)
        teachers = []
        if names:
            teachers = self.db.query(AcademicTeacher).filter(func.lower(AcademicTeacher.username).in_(names)).all()

        # Bank RBAC is scoped by the internal Question Bank subject id. AP data is scoped by
        # subject_code, so convert visible bank subjects to codes and combine it with AP
        # teacher assignments. This lets Department Head / Subject Owner see the AP subjects
        # they own, while normal teachers only see the classes AP assigned to them.
        subject_codes: set[str] = set()
        try:
            visible_subject_ids = self.rbac.accessible_subject_ids(user)
            if visible_subject_ids is None:
                return AccessDecision(unrestricted=True, teacher_ids=set(), subject_codes=set())
            if visible_subject_ids:
                rows = self.db.query(BankSubject.code).filter(BankSubject.id.in_(visible_subject_ids)).all()
                subject_codes = {str(row[0] or '').strip().lower() for row in rows if str(row[0] or '').strip()}
        except Exception:
            subject_codes = set()
        return AccessDecision(unrestricted=False, teacher_ids={item.id for item in teachers}, subject_codes=subject_codes)

    def assert_can_access_class(self, user: UserContext, class_id: str) -> None:
        decision = self.access_decision(user)
        if decision.unrestricted:
            return
        if not decision.teacher_ids and not decision.subject_codes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn chưa được phân quyền môn hoặc AP phân công lớp nào trên AI Server')
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
                AcademicSubject, AcademicSubject.id == AcademicClass.subject_id
            ).filter(
                AcademicClass.id == class_id,
                func.lower(AcademicSubject.subject_code).in_(decision.subject_codes),
            ).first()
            if subject_exists:
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
        query = self.db.query(AcademicSubject).filter(AcademicSubject.active.is_(True))
        if term_id or block_id:
            # Do not call DISTINCT over the full AcademicSubject row because metadata_json is
            # stored as PostgreSQL JSON, which has no equality operator. Select distinct IDs
            # from academic_classes first, then load subjects normally.
            subject_ids = self.db.query(AcademicClass.subject_id).filter(AcademicClass.subject_id.isnot(None))
            if term_id:
                subject_ids = subject_ids.filter(AcademicClass.term_id == term_id)
            if block_id:
                subject_ids = subject_ids.filter(AcademicClass.block_id == block_id)
            query = query.filter(AcademicSubject.id.in_(subject_ids.distinct()))
        if branch:
            query = query.filter(AcademicSubject.branch == branch.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))
        return query.order_by(AcademicSubject.subject_code.asc()).limit(500).all()

    def list_teacher_classes(
        self,
        user: UserContext,
        *,
        term_id: str | None = None,
        block_id: str | None = None,
        subject_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        search: str | None = None,
        learning_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        page, page_size = _page(page, page_size)
        decision = self.access_decision(user)
        status_filter = self._normalize_learning_list_filter(learning_status)
        needs_status_filter = status_filter != 'all'
        student_count_sq = self.db.query(
            AcademicClassStudent.class_id.label('class_id'),
            func.count(AcademicClassStudent.student_id).label('student_count'),
        ).group_by(AcademicClassStudent.class_id).subquery()

        # Aggregate teacher display fields per class so the main query remains
        # one row per class and avoids PostgreSQL DISTINCT ON ORDER BY traps.
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
        query = query.filter(AcademicClass.active.is_(True), AcademicSubject.active.is_(True))
        query = query.outerjoin(teacher_summary_sq, teacher_summary_sq.c.class_id == AcademicClass.id)
        query = query.outerjoin(student_count_sq, student_count_sq.c.class_id == AcademicClass.id)
        query = query.outerjoin(
            AcademicClassCourseMapping,
            and_(AcademicClassCourseMapping.class_id == AcademicClass.id, AcademicClassCourseMapping.active.is_(True)),
        )
        if not decision.unrestricted:
            access_conditions = []
            if decision.teacher_ids:
                allowed_class_ids = self.db.query(AcademicTeacherAssignment.class_id).filter(
                    AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids)
                )
                access_conditions.append(AcademicClass.id.in_(allowed_class_ids))
            if decision.subject_codes:
                access_conditions.append(func.lower(AcademicSubject.subject_code).in_(decision.subject_codes))
            if not access_conditions:
                return {'items': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0, 'has_next': False}
            query = query.filter(or_(*access_conditions))
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if block_id:
            query = query.filter(AcademicClass.block_id == block_id)
        if subject_id:
            query = query.filter(AcademicClass.subject_id == subject_id)
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(AcademicClass.campus == campus.strip().lower())
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
        ordered = query.order_by(AcademicTerm.start_date.desc().nullslast(), AcademicBlock.sort_order.asc().nullslast(), AcademicSubject.subject_code.asc(), AcademicClass.class_code.asc())
        base_total = query.count()
        rows = ordered.all() if needs_status_filter else ordered.offset((page - 1) * page_size).limit(page_size).all()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = row[0]
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
        classes_by_id = {row[0].id: row[0] for row in rows}
        inherited_mappings = self.inherited_course_mappings_for_classes(list(classes_by_id.values()))
        for entry in items:
            if entry.get('openedx_course_id'):
                continue
            inherited = inherited_mappings.get(entry['id'])
            if inherited:
                entry['openedx_course_id'] = inherited.openedx_course_id
                entry['openedx_cohort_name'] = entry['class_code']
                entry['openedx_mapping_source'] = 'subject_term_mapping'
                entry['openedx_mapping_validation_status'] = inherited.validation_status
        class_ids = [item['id'] for item in items]
        sync_by_class = self._student_sync_summary_for_classes(class_ids)
        for entry in items:
            counts = sync_by_class.get(entry['id'], {})
            entry['cms_synced_count'] = int(counts.get('matched', 0))
            entry['cms_unsynced_count'] = int(sum(v for k, v in counts.items() if k != 'matched'))
        learning_by_class = self._learning_summary_by_class_ids(class_ids, {item['id']: item.get('openedx_course_id') for item in items})
        for entry in items:
            entry.update(learning_by_class.get(entry['id'], {}))
        if needs_status_filter:
            items = [entry for entry in items if self._entry_matches_learning_list_filter(entry, status_filter)]
            total = len(items)
            items = items[(page - 1) * page_size:page * page_size]
        else:
            total = base_total
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}

    def _apply_academic_access_filter(self, query, user: UserContext, decision: AccessDecision | None = None):
        decision = decision or self.access_decision(user)
        if decision.unrestricted:
            return query
        access_conditions = []
        if decision.teacher_ids:
            allowed_class_ids = self.db.query(AcademicTeacherAssignment.class_id).filter(
                AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids)
            )
            access_conditions.append(AcademicClass.id.in_(allowed_class_ids))
        if decision.subject_codes:
            access_conditions.append(func.lower(AcademicSubject.subject_code).in_(decision.subject_codes))
        if not access_conditions:
            return query.filter(False)
        return query.filter(or_(*access_conditions))


    def _student_sync_summary_for_classes(self, class_ids: list[str]) -> dict[str, dict[str, int]]:
        if not class_ids:
            return {}
        rows = self.db.query(
            AcademicClassStudent.class_id.label('class_id'),
            OpenEdXUserMapping.match_status.label('match_status'),
            func.count(AcademicClassStudent.id).label('count'),
        ).outerjoin(
            OpenEdXUserMapping,
            OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
        ).filter(AcademicClassStudent.class_id.in_(class_ids)).group_by(
            AcademicClassStudent.class_id,
            OpenEdXUserMapping.match_status,
        ).all()
        result: dict[str, dict[str, int]] = {}
        for class_id, match_status, count in rows:
            bucket = result.setdefault(str(class_id), {})
            bucket[str(match_status or 'not_checked')] = int(count or 0)
        return result

    def _student_sync_summary_for_subjects(self, user: UserContext, term_id: str | None, subject_ids: list[str], branch: str | None = None, campus: str | None = None, decision: AccessDecision | None = None) -> dict[str, dict[str, int]]:
        if not subject_ids:
            return {}
        query = self.db.query(
            AcademicClass.subject_id.label('subject_id'),
            OpenEdXUserMapping.match_status.label('match_status'),
            func.count(AcademicClassStudent.id).label('count'),
        ).join(AcademicSubject, AcademicSubject.id == AcademicClass.subject_id).join(
            AcademicClassStudent, AcademicClassStudent.class_id == AcademicClass.id,
        ).outerjoin(
            OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
        ).filter(AcademicClass.subject_id.in_(subject_ids), AcademicClass.active.is_(True))
        query = self._apply_academic_access_filter(query, user, decision)
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(AcademicClass.campus == campus.strip().lower())
        rows = query.group_by(AcademicClass.subject_id, OpenEdXUserMapping.match_status).all()
        result: dict[str, dict[str, int]] = {}
        for subject_id, match_status, count in rows:
            bucket = result.setdefault(str(subject_id), {})
            bucket[str(match_status or 'not_checked')] = int(count or 0)
        return result


    @staticmethod
    def _number_or_none(value: Any) -> float | None:
        if value is None or value == '':
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _percent_display_value(value: Any) -> float | None:
        if value is None or value == '':
            return None
        try:
            number = float(value)
        except Exception:
            return None
        if 0 <= number <= 1:
            number *= 100.0
        return round(number, 2)

    def _normalize_component_score_item(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        key = str(
            item.get('key')
            or item.get('usage_key')
            or item.get('block_id')
            or item.get('id')
            or item.get('name')
            or item.get('display_name')
            or ''
        ).strip()
        name = str(
            item.get('name')
            or item.get('display_name')
            or item.get('label')
            or item.get('title')
            or key
            or 'Điểm thành phần'
        ).strip()
        earned = self._number_or_none(item.get('earned', item.get('earned_graded', item.get('score'))))
        possible = self._number_or_none(item.get('possible', item.get('possible_graded', item.get('max_score'))))
        percent = self._percent_display_value(item.get('percent', item.get('grade_percent', item.get('score_percent'))))
        if percent is None and earned is not None and possible and possible > 0:
            percent = round((earned / possible) * 100.0, 2)
        if percent is None and earned is None and possible is None:
            return None
        return {
            'key': key or name,
            'name': name[:255],
            'category': str(item.get('category') or item.get('type') or item.get('format') or item.get('block_type') or '').strip() or None,
            'earned': round(earned, 2) if earned is not None else None,
            'possible': round(possible, 2) if possible is not None else None,
            'percent': percent,
            'weight': self._number_or_none(item.get('weight')),
            'source': str(item.get('source') or item.get('model') or '').strip() or None,
        }

    def _component_scores_from_payload(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        candidate_lists: list[Any] = []
        for key in ('component_scores', 'component_grades', 'grade_components', 'subsection_grades', 'section_scores', 'scores'):
            candidate_lists.append(payload.get(key))
        grade = payload.get('grade') if isinstance(payload.get('grade'), dict) else {}
        for key in ('components', 'component_scores', 'component_grades', 'subsection_grades', 'section_scores', 'breakdown'):
            candidate_lists.append(grade.get(key))
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidate_lists:
            if isinstance(candidate, dict):
                iterable = []
                for key, value in candidate.items():
                    if isinstance(value, dict):
                        iterable.append({'key': key, **value})
                candidate = iterable
            if not isinstance(candidate, list):
                continue
            for raw_item in candidate:
                item = self._normalize_component_score_item(raw_item)
                if not item:
                    continue
                dedupe = str(item.get('key') or item.get('name') or '').lower()
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                normalized.append(item)
        normalized.sort(key=lambda item: str(item.get('name') or item.get('key') or ''))
        return normalized[:30]

    def _component_scores_from_snapshot(self, snapshot: AcademicStudentLearningSnapshot | None) -> list[dict[str, Any]]:
        if not snapshot or not isinstance(snapshot.raw_json, dict):
            return []
        raw = snapshot.raw_json
        payload = raw.get('payload') if isinstance(raw.get('payload'), dict) else raw
        return self._component_scores_from_payload(payload)

    def _low_progress_threshold(self) -> float:
        try:
            return float(getattr(settings, 'academic_learning_low_progress_threshold_percent', 50.0))
        except Exception:
            return 50.0

    def _low_grade_threshold(self) -> float:
        try:
            return float(getattr(settings, 'academic_learning_low_grade_threshold_percent', 50.0))
        except Exception:
            return 50.0

    @staticmethod
    def _snapshot_has_learning_activity(snapshot: AcademicStudentLearningSnapshot | None) -> bool:
        if not snapshot:
            return False
        if str(snapshot.enrollment_status or '').lower() != 'enrolled':
            return False
        progress = snapshot.progress_percent
        grade = snapshot.grade_percent
        completed = snapshot.completed_blocks or 0
        if progress is not None and progress > 0:
            return True
        if grade is not None:
            return True
        if completed and completed > 0:
            return True
        if snapshot.last_activity_at is not None:
            return True
        return False

    def _learning_status_for_snapshot(self, snapshot: AcademicStudentLearningSnapshot | None, mapping: OpenEdXUserMapping | None = None) -> str:
        if mapping is None or (mapping.match_status or '') != 'matched':
            return 'cms_not_synced'
        if not snapshot:
            return 'not_synced'
        enrollment_status = str(snapshot.enrollment_status or '').lower()
        if enrollment_status in {'failed', 'missing_user', 'inactive_user', 'unknown'}:
            return 'sync_error'
        if enrollment_status != 'enrolled':
            return 'not_enrolled'
        progress = snapshot.progress_percent
        grade = snapshot.grade_percent
        if not self._snapshot_has_learning_activity(snapshot):
            return 'no_activity'
        if grade is not None and grade < self._low_grade_threshold():
            return 'low_grade'
        if progress is not None and progress < self._low_progress_threshold():
            return 'low_progress'
        if snapshot.passed is True or (grade is not None and grade >= 80) or (progress is not None and progress >= 80):
            return 'good'
        return 'in_progress'

    def _component_summary_from_snapshots(self, snapshots: list[AcademicStudentLearningSnapshot]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            for item in self._component_scores_from_snapshot(snapshot):
                key = str(item.get('key') or item.get('name') or '').strip()
                if not key:
                    continue
                bucket = buckets.setdefault(key, {'key': key, 'name': item.get('name') or key, 'category': item.get('category'), 'percents': [], 'earned': 0.0, 'possible': 0.0, 'student_count': 0})
                percent = self._percent_display_value(item.get('percent'))
                if percent is not None:
                    bucket['percents'].append(percent)
                earned = self._number_or_none(item.get('earned'))
                possible = self._number_or_none(item.get('possible'))
                if earned is not None:
                    bucket['earned'] += earned
                if possible is not None:
                    bucket['possible'] += possible
                bucket['student_count'] += 1
        results: list[dict[str, Any]] = []
        for bucket in buckets.values():
            percents = bucket.pop('percents')
            if percents:
                percent = round(sum(percents) / len(percents), 2)
            elif bucket.get('possible'):
                percent = round((bucket.get('earned', 0.0) / bucket['possible']) * 100.0, 2)
            else:
                percent = None
            results.append({
                'key': bucket['key'],
                'name': bucket['name'],
                'category': bucket.get('category'),
                'earned': round(bucket.get('earned', 0.0), 2) if bucket.get('earned') else None,
                'possible': round(bucket.get('possible', 0.0), 2) if bucket.get('possible') else None,
                'percent': percent,
                'weight': None,
                'source': f"{bucket.get('student_count', 0)} SV",
            })
        results.sort(key=lambda item: (item.get('percent') is None, str(item.get('name') or '')))
        return results[:20]

    def _learning_alerts_from_summary(self, *, total: int, enrolled: int, synced: int, active: int = 0, avg_progress: float | None, avg_grade: float | None, course_id: str | None) -> list[str]:
        alerts: list[str] = []
        if not course_id:
            alerts.append('Chưa map Course CMS')
        if total and synced == 0:
            alerts.append('Chưa có dữ liệu học tập')
        if total and enrolled < total:
            alerts.append(f'{total - enrolled} SV chưa enroll')
        if synced and active == 0:
            alerts.append('Chưa có sinh viên vào học')
        if avg_progress is not None and avg_progress < self._low_progress_threshold():
            alerts.append('Tiến độ thấp')
        if avg_grade is not None and avg_grade < self._low_grade_threshold():
            alerts.append('Điểm thấp')
        return alerts

    @staticmethod
    def _normalize_learning_list_filter(value: str | None) -> str:
        raw = str(value or '').strip().lower()
        aliases = {
            'all': 'all', 'tat_ca': 'all', '': 'all',
            'no_course_map': 'no_course_map', 'not_mapped': 'no_course_map',
            'cms_not_synced': 'cms_not_synced', 'not_cms_synced': 'cms_not_synced',
            'not_fully_enrolled': 'not_fully_enrolled', 'not_enrolled': 'not_fully_enrolled',
            'no_progress': 'no_learning_data', 'no_learning': 'no_learning_data', 'no_learning_data': 'no_learning_data',
            'no_activity': 'no_activity',
            'low_progress': 'low_progress', 'low_grade': 'low_grade',
            'sync_error': 'sync_error', 'has_alert': 'has_alert', 'warning': 'has_alert',
        }
        return aliases.get(raw, raw or 'all')

    def _entry_matches_learning_list_filter(self, entry: dict[str, Any], status_filter: str | None) -> bool:
        status = self._normalize_learning_list_filter(status_filter)
        if status == 'all':
            return True
        total = int(entry.get('student_count') or 0)
        course_id = entry.get('openedx_course_id')
        enrolled = int(entry.get('learning_enrolled_count') or 0)
        synced = int(entry.get('learning_synced_count') or 0)
        active = int(entry.get('learning_active_count') or 0)
        cms_synced = int(entry.get('cms_synced_count') or 0)
        cms_unsynced = int(entry.get('cms_unsynced_count') or 0)
        avg_progress = entry.get('learning_avg_progress_percent')
        avg_grade = entry.get('learning_avg_grade_percent')
        alerts = entry.get('learning_alerts') or []
        if status == 'no_course_map':
            if 'course_mapping_status' in entry:
                return str(entry.get('course_mapping_status') or '').lower() not in {'mapped', 'already_mapped', 'auto_mapped'}
            return not bool(course_id)
        if status == 'cms_not_synced':
            return total > 0 and (cms_unsynced > 0 or cms_synced < total)
        if status == 'not_fully_enrolled':
            return total > 0 and enrolled < total
        if status == 'no_learning_data':
            return total > 0 and synced == 0
        if status == 'no_activity':
            return total > 0 and synced > 0 and active == 0
        if status == 'low_progress':
            return isinstance(avg_progress, (int, float)) and avg_progress < self._low_progress_threshold()
        if status == 'low_grade':
            return isinstance(avg_grade, (int, float)) and avg_grade < self._low_grade_threshold()
        if status == 'sync_error':
            return any('lỗi' in str(item).lower() for item in alerts)
        if status == 'has_alert':
            return bool(alerts)
        return True

    def _learning_summary_by_class_ids(self, class_ids: list[str], course_by_class: dict[str, str | None] | None = None) -> dict[str, dict[str, Any]]:
        if not class_ids:
            return {}
        totals = dict(self.db.query(AcademicClassStudent.class_id, func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id.in_(class_ids)).group_by(AcademicClassStudent.class_id).all())
        snapshot_query = self.db.query(AcademicStudentLearningSnapshot).filter(AcademicStudentLearningSnapshot.class_id.in_(class_ids))
        expected_courses = {course for course in (course_by_subject or {}).values() if course}
        if expected_courses:
            snapshot_query = snapshot_query.filter(AcademicStudentLearningSnapshot.openedx_course_id.in_(sorted(expected_courses)))
        snapshots = snapshot_query.all()
        buckets: dict[str, dict[str, Any]] = {cid: {'snapshots': [], 'counts': {}, 'progress': [], 'grades': [], 'active': 0, 'last_synced_at': None} for cid in class_ids}
        for snapshot in snapshots:
            expected_course = (course_by_class or {}).get(snapshot.class_id)
            if expected_course and snapshot.openedx_course_id != expected_course:
                continue
            bucket = buckets.setdefault(snapshot.class_id, {'snapshots': [], 'counts': {}, 'progress': [], 'grades': [], 'active': 0, 'last_synced_at': None})
            bucket['snapshots'].append(snapshot)
            status_value = str(snapshot.enrollment_status or 'unknown')
            bucket['counts'][status_value] = bucket['counts'].get(status_value, 0) + 1
            if snapshot.progress_percent is not None:
                bucket['progress'].append(float(snapshot.progress_percent))
            if snapshot.grade_percent is not None:
                bucket['grades'].append(float(snapshot.grade_percent))
            if self._snapshot_has_learning_activity(snapshot):
                bucket['active'] = int(bucket.get('active', 0) or 0) + 1
            sync_at = snapshot.learning_synced_at or snapshot.last_synced_at
            if sync_at and (bucket['last_synced_at'] is None or sync_at > bucket['last_synced_at']):
                bucket['last_synced_at'] = sync_at
        result: dict[str, dict[str, Any]] = {}
        for class_id, bucket in buckets.items():
            total = int(totals.get(class_id, 0) or 0)
            counts = dict(bucket['counts'])
            synced = len(bucket['snapshots'])
            enrolled = int(counts.get('enrolled', 0) or 0)
            avg_progress = round(sum(bucket['progress']) / len(bucket['progress']), 2) if bucket['progress'] else None
            avg_grade = round(sum(bucket['grades']) / len(bucket['grades']), 2) if bucket['grades'] else None
            course_id = (course_by_class or {}).get(class_id)
            result[class_id] = {
                'learning_enrolled_count': enrolled,
                'learning_active_count': int(bucket.get('active', 0) or 0),
                'learning_synced_count': synced,
                'learning_not_enrolled_count': max(0, total - enrolled),
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_last_synced_at': bucket['last_synced_at'],
                'learning_component_summaries': self._component_summary_from_snapshots(bucket['snapshots']),
                'learning_alerts': self._learning_alerts_from_summary(total=total, enrolled=enrolled, synced=synced, active=int(bucket.get('active', 0) or 0), avg_progress=avg_progress, avg_grade=avg_grade, course_id=course_id),
            }
        return result

    def _learning_summary_by_subject_ids(self, subject_ids: list[str], *, term_id: str | None = None, branch: str | None = None, campus: str | None = None, course_by_subject: dict[str, str | None] | None = None, decision: AccessDecision | None = None, user: UserContext | None = None) -> dict[str, dict[str, Any]]:
        if not subject_ids:
            return {}
        class_query = self.db.query(AcademicClass.id, AcademicClass.subject_id).join(AcademicSubject, AcademicSubject.id == AcademicClass.subject_id).filter(AcademicClass.subject_id.in_(subject_ids), AcademicClass.active.is_(True))
        if user is not None:
            class_query = self._apply_academic_access_filter(class_query, user, decision)
        if term_id:
            class_query = class_query.filter(AcademicClass.term_id == term_id)
        if branch:
            class_query = class_query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            class_query = class_query.filter(AcademicClass.campus == campus.strip().lower())
        pairs = class_query.all()
        class_to_subject = {str(cid): str(sid) for cid, sid in pairs}
        class_ids = list(class_to_subject.keys())
        if not class_ids:
            return {sid: {'learning_enrolled_count': 0, 'learning_active_count': 0, 'learning_synced_count': 0, 'learning_not_enrolled_count': 0, 'learning_avg_progress_percent': None, 'learning_avg_grade_percent': None, 'learning_last_synced_at': None, 'learning_component_summaries': [], 'learning_alerts': ['Chưa có lớp active']} for sid in subject_ids}
        totals_rows = self.db.query(AcademicClass.subject_id, func.count(AcademicClassStudent.id)).join(AcademicClassStudent, AcademicClassStudent.class_id == AcademicClass.id).filter(AcademicClass.id.in_(class_ids)).group_by(AcademicClass.subject_id).all()
        totals = {str(subject_id): int(count or 0) for subject_id, count in totals_rows}
        snapshot_query = self.db.query(AcademicStudentLearningSnapshot).filter(AcademicStudentLearningSnapshot.class_id.in_(class_ids))
        expected_courses = {course for course in (course_by_subject or {}).values() if course}
        if expected_courses:
            snapshot_query = snapshot_query.filter(AcademicStudentLearningSnapshot.openedx_course_id.in_(sorted(expected_courses)))
        snapshots = snapshot_query.all()
        buckets: dict[str, dict[str, Any]] = {sid: {'snapshots': [], 'counts': {}, 'progress': [], 'grades': [], 'active': 0, 'last_synced_at': None} for sid in subject_ids}
        for snapshot in snapshots:
            subject_id = class_to_subject.get(snapshot.class_id)
            if not subject_id:
                continue
            expected_course = (course_by_subject or {}).get(subject_id)
            if expected_course and snapshot.openedx_course_id != expected_course:
                continue
            bucket = buckets.setdefault(subject_id, {'snapshots': [], 'counts': {}, 'progress': [], 'grades': [], 'active': 0, 'last_synced_at': None})
            bucket['snapshots'].append(snapshot)
            status_value = str(snapshot.enrollment_status or 'unknown')
            bucket['counts'][status_value] = bucket['counts'].get(status_value, 0) + 1
            if snapshot.progress_percent is not None:
                bucket['progress'].append(float(snapshot.progress_percent))
            if snapshot.grade_percent is not None:
                bucket['grades'].append(float(snapshot.grade_percent))
            if self._snapshot_has_learning_activity(snapshot):
                bucket['active'] = int(bucket.get('active', 0) or 0) + 1
            sync_at = snapshot.learning_synced_at or snapshot.last_synced_at
            if sync_at and (bucket['last_synced_at'] is None or sync_at > bucket['last_synced_at']):
                bucket['last_synced_at'] = sync_at
        result: dict[str, dict[str, Any]] = {}
        for subject_id, bucket in buckets.items():
            total = int(totals.get(subject_id, 0) or 0)
            counts = dict(bucket['counts'])
            synced = len(bucket['snapshots'])
            enrolled = int(counts.get('enrolled', 0) or 0)
            avg_progress = round(sum(bucket['progress']) / len(bucket['progress']), 2) if bucket['progress'] else None
            avg_grade = round(sum(bucket['grades']) / len(bucket['grades']), 2) if bucket['grades'] else None
            course_id = (course_by_subject or {}).get(subject_id)
            result[subject_id] = {
                'learning_enrolled_count': enrolled,
                'learning_active_count': int(bucket.get('active', 0) or 0),
                'learning_synced_count': synced,
                'learning_not_enrolled_count': max(0, total - enrolled),
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_last_synced_at': bucket['last_synced_at'],
                'learning_component_summaries': self._component_summary_from_snapshots(bucket['snapshots']),
                'learning_alerts': self._learning_alerts_from_summary(total=total, enrolled=enrolled, synced=synced, active=int(bucket.get('active', 0) or 0), avg_progress=avg_progress, avg_grade=avg_grade, course_id=course_id),
            }
        return result

    def _find_exact_openedx_course_candidate(self, openedx_course_id: str, *, allow_external: bool = False) -> tuple[str | None, int, str | None, str]:
        raw = str(openedx_course_id or '').strip()
        if not raw:
            return None, 0, None, 'empty'
        cache = getattr(self, '_openedx_course_candidate_cache', None)
        if cache is None:
            cache = {}
            setattr(self, '_openedx_course_candidate_cache', cache)
        cache_key = raw.lower()
        if cache_key in cache:
            return cache[cache_key]

        rows = self.db.query(CourseSyncState.course_id, CourseSyncState.display_name).filter(
            func.lower(CourseSyncState.course_id) == raw.lower(),
        ).distinct().limit(2).all()
        if len(rows) == 1:
            result = (str(rows[0][0]), 1, str(rows[0][1] or '') or None, 'local_course_sync_state')
            cache[cache_key] = result
            return result

        # Do not call CMS/Open edX from normal read/list APIs. Student
        # Management pages refresh often, and a GET/F5 must stay local-db only.
        # External lookup is allowed only from explicit actions such as
        # /course-mapping/auto or validation/save flows.
        if not allow_external:
            result = (None, len(rows), None, 'local_course_sync_state')
            cache[cache_key] = result
            return result

        # Explicit API-first autofill fallback: if the course has not been synced
        # into CourseSyncState yet, ask CMS/Open edX directly only after the user
        # triggers auto-map/validate.
        try:
            candidate, title, count, source = OpenEdXStudentInsightClient().find_exact_course(raw)
            if count == 1 and candidate:
                result = (candidate, 1, title, source)
                cache[cache_key] = result
                return result
            if count > 0:
                result = (None, count, None, source)
                cache[cache_key] = result
                return result
        except Exception:
            pass

        result = (None, len(rows), None, 'local_course_sync_state')
        cache[cache_key] = result
        return result

    def _auto_create_subject_course_mapping_if_safe(
        self,
        user: UserContext,
        *,
        term_id: str,
        subject_id: str,
        branch_value: str | None,
        candidate: str,
        suggested: str,
        openedx_course_title: str | None = None,
        candidate_source: str = 'unknown',
        commit: bool = False,
    ) -> AcademicCourseMapping | None:
        current = self._scope_filter_course_mapping(
            term_id=term_id,
            block_id=None,
            subject_id=subject_id,
            campus=None,
            branch=branch_value,
        ).first()
        if current:
            return current
        validation = self.validate_course_mapping_payload(
            term_id=term_id,
            subject_id=subject_id,
            openedx_course_id=candidate,
            block_id=None,
            campus=None,
            branch=branch_value,
            openedx_course_title=openedx_course_title,
        )
        if not validation.get('can_save'):
            return None
        now = datetime.utcnow()
        mapping = AcademicCourseMapping(
            term_id=term_id,
            block_id=None,
            subject_id=subject_id,
            campus=None,
            branch=branch_value,
            openedx_course_id=candidate,
            openedx_course_title=openedx_course_title,
            validation_status='auto_mapped',
            validation_json={**validation, 'auto_map': True, 'auto_map_rule': 'exact subject_code + term_run course_id', 'suggested_openedx_course_id': suggested, 'candidate_source': candidate_source},
            validated_at=now,
            created_by=user.user_id or user.username or 'system_auto',
            updated_by=user.user_id or user.username or 'system_auto',
            note=f'Auto map an toàn theo mã môn + kỳ; chỉ chạy khi tìm thấy đúng một Course CMS khớp. Nguồn: {candidate_source}.',
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(mapping)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(mapping)
        return mapping

    def auto_map_subject_course(self, user: UserContext, *, term_id: str, subject_id: str, branch: str | None = None) -> dict[str, Any]:
        self.assert_can_access_subject(user, subject_id)
        term = self.db.get(AcademicTerm, term_id)
        subject = self.db.get(AcademicSubject, subject_id)
        if not term or not subject:
            raise HTTPException(status_code=404, detail='Không tìm thấy kỳ hoặc môn AP')
        branch_value = (branch or subject.branch or term.branch or '').strip().lower() or None
        current = self._scope_filter_course_mapping(
            term_id=term_id,
            block_id=None,
            subject_id=subject_id,
            campus=None,
            branch=branch_value,
        ).first()
        suggested = self.suggested_course_id_for_scope(term_id, subject_id)
        if current:
            return {
                'ok': True,
                'status': 'already_mapped',
                'message': 'Môn đã có mapping Course CMS.',
                'suggested_openedx_course_id': suggested,
                'mapping': self._course_mapping_item(current),
            }
        candidate, candidate_count, candidate_title, candidate_source = self._find_exact_openedx_course_candidate(suggested, allow_external=True)
        if candidate_count != 1 or not candidate:
            status_value = 'not_found' if candidate_count == 0 else 'multiple_candidates'
            return {
                'ok': False,
                'status': status_value,
                'message': 'Chưa tìm thấy đúng một Course CMS khớp mã môn/kỳ từ dữ liệu local hoặc API CMS/Open edX.',
                'suggested_openedx_course_id': suggested,
                'mapping': None,
            }
        mapping = self._auto_create_subject_course_mapping_if_safe(
            user,
            term_id=term_id,
            subject_id=subject_id,
            branch_value=branch_value,
            candidate=candidate,
            suggested=suggested,
            openedx_course_title=candidate_title,
            candidate_source=candidate_source,
            commit=True,
        )
        if not mapping:
            return {
                'ok': False,
                'status': 'validation_failed',
                'message': 'Course tìm thấy nhưng không đạt điều kiện mapping an toàn.',
                'suggested_openedx_course_id': suggested,
                'mapping': None,
            }
        return {
            'ok': True,
            'status': 'auto_mapped',
            'message': 'Đã tự động map môn với Course CMS.',
            'suggested_openedx_course_id': suggested,
            'mapping': self._course_mapping_item(mapping),
        }

    def list_teacher_subjects(
        self,
        user: UserContext,
        *,
        term_id: str | None = None,
        branch: str | None = None,
        campus: str | None = None,
        search: str | None = None,
        learning_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        page, page_size = _page(page, page_size)
        decision = self.access_decision(user)
        status_filter = self._normalize_learning_list_filter(learning_status)
        needs_status_filter = status_filter != 'all'
        query = self.db.query(
            AcademicSubject,
            func.count(func.distinct(AcademicClass.id)).label('class_count'),
            func.count(func.distinct(AcademicClass.campus)).label('campus_count'),
            func.count(func.distinct(AcademicTeacherAssignment.teacher_id)).label('teacher_count'),
            func.count(func.distinct(AcademicClassStudent.id)).label('student_count'),
        ).join(AcademicClass, AcademicClass.subject_id == AcademicSubject.id).outerjoin(
            AcademicTeacherAssignment, AcademicTeacherAssignment.class_id == AcademicClass.id,
        ).outerjoin(AcademicClassStudent, AcademicClassStudent.class_id == AcademicClass.id).filter(AcademicSubject.active.is_(True), AcademicClass.active.is_(True))
        query = self._apply_academic_access_filter(query, user, decision)
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(AcademicClass.campus == campus.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))
        query = query.group_by(AcademicSubject.id)
        ordered = query.order_by(AcademicSubject.subject_code.asc())
        base_total = query.count()
        rows = ordered.all() if needs_status_filter else ordered.offset((page - 1) * page_size).limit(page_size).all()
        subject_ids = [row[0].id for row in rows]
        mapping_rows = []
        if subject_ids and term_id:
            mapping_query = self.db.query(AcademicCourseMapping).filter(
                AcademicCourseMapping.term_id == term_id,
                AcademicCourseMapping.subject_id.in_(subject_ids),
                AcademicCourseMapping.active.is_(True),
                AcademicCourseMapping.block_id.is_(None),
                AcademicCourseMapping.campus.is_(None),
            )
            if branch:
                mapping_query = mapping_query.filter(AcademicCourseMapping.branch == branch.strip().lower())
            mapping_rows = mapping_query.all()
        mapping_by_subject = {item.subject_id: item for item in mapping_rows}
        sync_summary = self._student_sync_summary_for_subjects(user, term_id, subject_ids, branch=branch, campus=campus, decision=decision)
        items: list[dict[str, Any]] = []
        for row in rows:
            subject = row[0]
            mapping = mapping_by_subject.get(subject.id)
            suggested = self.suggested_course_id_for_scope(term_id, subject.id) if term_id else None
            candidate, candidate_count, candidate_title, _candidate_source = self._find_exact_openedx_course_candidate(suggested or '', allow_external=False)
            if mapping:
                status_value = 'mapped'
                status_label = 'Đã map Course CMS'
                effective_course_id = mapping.openedx_course_id
            elif candidate_count == 1 and candidate and term_id:
                # GET/list APIs must not create or commit mappings. They only show a safe candidate;
                # the actual mapping is created by the explicit Auto map button.
                status_value = 'auto_candidate'
                status_label = 'Có thể auto map'
                effective_course_id = candidate
            elif candidate_count > 1:
                status_value = 'multiple_candidates'
                status_label = 'Nhiều course trùng'
                effective_course_id = None
            else:
                status_value = 'not_found'
                status_label = 'Chưa tìm thấy course'
                effective_course_id = None
            counts = sync_summary.get(subject.id, {})
            items.append({
                'id': subject.id,
                'ap_subject_id': subject.ap_subject_id,
                'subject_code': subject.subject_code,
                'subject_name': subject.subject_name,
                'subject_name_en': subject.subject_name_en,
                'skill_code': subject.skill_code,
                'branch': subject.branch,
                'active': subject.active,
                'class_count': int(row.class_count or 0),
                'campus_count': int(row.campus_count or 0),
                'teacher_count': int(row.teacher_count or 0),
                'student_count': int(row.student_count or 0),
                'cms_synced_count': int(counts.get('matched', 0)),
                'cms_unsynced_count': int(sum(v for k, v in counts.items() if k not in {'matched'})),
                'course_mapping_status': status_value,
                'course_mapping_label': status_label,
                'openedx_course_id': mapping.openedx_course_id if mapping else effective_course_id,
                'openedx_course_title': mapping.openedx_course_title if mapping else candidate_title,
                'openedx_mapping_id': mapping.id if mapping else None,
                'suggested_openedx_course_id': suggested,
            })
        learning_by_subject = self._learning_summary_by_subject_ids(
            subject_ids,
            term_id=term_id,
            branch=branch,
            campus=campus,
            course_by_subject={item['id']: item.get('openedx_course_id') for item in items},
            decision=decision,
            user=user,
        )
        for entry in items:
            entry.update(learning_by_subject.get(entry['id'], {}))
        if needs_status_filter:
            items = [entry for entry in items if self._entry_matches_learning_list_filter(entry, status_filter)]
            total = len(items)
            items = items[(page - 1) * page_size:page * page_size]
        else:
            total = base_total
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}

    def get_class_detail(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        term = self.db.get(AcademicTerm, cls.term_id)
        block = self.db.get(AcademicBlock, cls.block_id) if cls.block_id else None
        subject = self.db.get(AcademicSubject, cls.subject_id)
        class_mapping = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id == cls.id,
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).first()
        inherited = None if class_mapping else self.inherited_course_mapping_for_class(cls)
        student_count = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == cls.id).scalar() or 0
        class_sync_counts = self._student_sync_summary_for_classes([cls.id]).get(cls.id, {})
        teacher = self.db.query(AcademicTeacher).join(
            AcademicTeacherAssignment, AcademicTeacherAssignment.teacher_id == AcademicTeacher.id,
        ).filter(AcademicTeacherAssignment.class_id == cls.id).order_by(AcademicTeacher.username.asc()).first()

        effective_mapping = class_mapping or inherited
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
            'cms_synced_count': int(class_sync_counts.get('matched', 0)),
            'cms_unsynced_count': int(sum(v for k, v in class_sync_counts.items() if k != 'matched')),
            'openedx_course_id': effective_mapping.openedx_course_id if effective_mapping else None,
            'openedx_cohort_name': class_mapping.openedx_cohort_name if class_mapping else (cls.class_code if inherited else None),
            'openedx_mapping_source': 'class_override' if class_mapping else ('subject_term_mapping' if inherited else None),
            'openedx_mapping_validation_status': effective_mapping.validation_status if effective_mapping else None,
        }

    def _student_mapping_item(self, class_id: str, student: AcademicStudent, synced_at: datetime | None, mapping: OpenEdXUserMapping | None, learning: AcademicStudentLearningSnapshot | None = None) -> dict[str, Any]:
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
            'learning_snapshot_id': learning.id if learning else None,
            'learning_enrollment_status': learning.enrollment_status if learning else None,
            'learning_enrollment_mode': learning.enrollment_mode if learning else None,
            'learning_progress_percent': learning.progress_percent if learning else None,
            'learning_grade_percent': learning.grade_percent if learning else None,
            'learning_passed': learning.passed if learning else None,
            'learning_completed_blocks': learning.completed_blocks if learning else None,
            'learning_total_blocks': learning.total_blocks if learning else None,
            'learning_last_activity_at': learning.last_activity_at if learning else None,
            'learning_last_synced_at': (learning.learning_synced_at or learning.last_synced_at) if learning else None,
            'learning_enrollment_synced_at': learning.enrollment_synced_at if learning else None,
            'learning_status': self._learning_status_for_snapshot(learning, mapping),
            'learning_component_scores': self._component_scores_from_snapshot(learning),
        }

    def list_class_students(self, user: UserContext, class_id: str, *, search: str | None = None, learning_status: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        page, page_size = _page(page, page_size)
        cls = self.db.get(AcademicClass, class_id)
        effective_mapping = self.effective_course_mapping_for_class(cls) if cls else None
        course_id = effective_mapping.openedx_course_id if effective_mapping else None
        query = self.db.query(AcademicStudent, AcademicClassStudent.synced_at, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
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
            if status_filter == 'cms_not_synced':
                query = query.filter(or_(OpenEdXUserMapping.id.is_(None), OpenEdXUserMapping.match_status != 'matched'))
            elif status_filter == 'not_enrolled':
                query = query.filter(or_(AcademicStudentLearningSnapshot.id.is_(None), AcademicStudentLearningSnapshot.enrollment_status != 'enrolled'))
            elif status_filter == 'no_activity':
                query = query.filter(or_(
                    AcademicStudentLearningSnapshot.id.is_(None),
                    and_(AcademicStudentLearningSnapshot.enrollment_status == 'enrolled', AcademicStudentLearningSnapshot.progress_percent.is_(None), AcademicStudentLearningSnapshot.grade_percent.is_(None)),
                    and_(AcademicStudentLearningSnapshot.enrollment_status == 'enrolled', AcademicStudentLearningSnapshot.progress_percent <= 0, AcademicStudentLearningSnapshot.grade_percent.is_(None)),
                ))
            elif status_filter == 'low_progress':
                query = query.filter(AcademicStudentLearningSnapshot.progress_percent.isnot(None), AcademicStudentLearningSnapshot.progress_percent < self._low_progress_threshold())
            elif status_filter == 'low_grade':
                query = query.filter(AcademicStudentLearningSnapshot.grade_percent.isnot(None), AcademicStudentLearningSnapshot.grade_percent < self._low_grade_threshold())
            elif status_filter == 'sync_error':
                query = query.filter(or_(
                    AcademicStudentLearningSnapshot.enrollment_status.in_(['failed', 'unknown', 'missing_user', 'inactive_user']),
                    OpenEdXUserMapping.match_status.in_(['inactive', 'ambiguous', 'manual_required']),
                ))
        total = query.count()
        rows = query.order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).offset((page - 1) * page_size).limit(page_size).all()
        items = [self._student_mapping_item(class_id, student, synced_at, mapping, learning) for student, synced_at, mapping, learning in rows]
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
        return self.inherited_course_mappings_for_classes([cls]).get(cls.id) if cls else None

    def inherited_course_mappings_for_classes(self, classes: list[AcademicClass]) -> dict[str, AcademicCourseMapping]:
        """Resolve inherited subject/term mappings for many classes without N+1 queries."""
        valid_classes = [cls for cls in classes if cls and cls.id and cls.term_id and cls.subject_id]
        if not valid_classes:
            return {}
        term_ids = {cls.term_id for cls in valid_classes}
        subject_ids = {cls.subject_id for cls in valid_classes}
        mappings = self.db.query(AcademicCourseMapping).filter(
            AcademicCourseMapping.term_id.in_(term_ids),
            AcademicCourseMapping.subject_id.in_(subject_ids),
            AcademicCourseMapping.active.is_(True),
        ).order_by(AcademicCourseMapping.updated_at.desc().nullslast(), AcademicCourseMapping.created_at.desc().nullslast()).all()

        def matches(value: str | None, expected: str | None) -> bool:
            return value == expected

        def priority(cls: AcademicClass, mapping: AcademicCourseMapping) -> int | None:
            if mapping.term_id != cls.term_id or mapping.subject_id != cls.subject_id:
                return None
            order = [
                (cls.block_id, cls.campus, cls.branch),
                (cls.block_id, None, cls.branch),
                (cls.block_id, cls.campus, None),
                (cls.block_id, None, None),
                (None, cls.campus, cls.branch),
                (None, None, cls.branch),
                (None, cls.campus, None),
                (None, None, None),
            ]
            candidate = (mapping.block_id, mapping.campus, mapping.branch)
            for index, expected in enumerate(order):
                if all(matches(candidate[i], expected[i]) for i in range(3)):
                    return index
            return None

        result: dict[str, AcademicCourseMapping] = {}
        best_rank: dict[str, int] = {}
        for cls in valid_classes:
            for mapping in mappings:
                rank = priority(cls, mapping)
                if rank is None:
                    continue
                if cls.id not in best_rank or rank < best_rank[cls.id]:
                    result[cls.id] = mapping
                    best_rank[cls.id] = rank
                    if rank == 0:
                        break
        return result

    def effective_course_mapping_for_class(self, cls: AcademicClass | None) -> AcademicClassCourseMapping | AcademicCourseMapping | None:
        """Return the exact course mapping used by every class-level operation.

        Class override wins over subject/term inherited mapping. All enrollment,
        learning sync, detail, and student list flows must use this helper so a
        class-specific Open edX course/cohort cannot be displayed in one screen
        while another syncs against the inherited course.
        """
        if not cls:
            return None
        class_mapping = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id == cls.id,
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).first()
        if class_mapping:
            return class_mapping
        return self.inherited_course_mapping_for_class(cls)

    def _cohort_for_class_mapping(self, cls: AcademicClass, mapping: AcademicClassCourseMapping | AcademicCourseMapping | None) -> str | None:
        if isinstance(mapping, AcademicClassCourseMapping):
            return mapping.openedx_cohort_name or cls.class_code
        return cls.class_code if mapping else None

    @staticmethod
    def _snapshot_has_learning_payload(snapshot: AcademicStudentLearningSnapshot | None) -> bool:
        if not snapshot:
            return False
        if snapshot.progress_percent is not None or snapshot.grade_percent is not None:
            return True
        if snapshot.completed_blocks is not None or snapshot.total_blocks is not None:
            return True
        raw = snapshot.raw_json if isinstance(snapshot.raw_json, dict) else {}
        payload = raw.get('payload') if isinstance(raw.get('payload'), dict) else {}
        component_scores = payload.get('component_scores') or payload.get('component_grades')
        return bool(component_scores)

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

    def _teacher_payload_for_class(self, class_id: str) -> list[tuple[AcademicTeacher, dict[str, Any]]]:
        rows = self.db.query(AcademicTeacher).join(
            AcademicTeacherAssignment,
            AcademicTeacherAssignment.teacher_id == AcademicTeacher.id,
        ).filter(
            AcademicTeacherAssignment.class_id == class_id,
            AcademicTeacher.active.is_(True),
        ).order_by(AcademicTeacher.username.asc()).all()
        payload: list[tuple[AcademicTeacher, dict[str, Any]]] = []
        seen: set[str] = set()
        for teacher in rows:
            username = normalize_username(teacher.username)
            if not username or username in seen:
                continue
            seen.add(username)
            payload.append((teacher, {
                'username': username,
                'teacher': username,
                'person_type': 'teacher',
                'role': 'teacher',
                'email': teacher.email or f'{username}@fpt.edu.vn',
                'full_name': teacher.full_name or username,
                'first_name': username,
                'last_name': username,
                'create_missing': True,
            }))
        return payload

    def _upsert_teacher_cms_metadata(self, teacher: AcademicTeacher, result: dict[str, Any] | None) -> str:
        now = datetime.utcnow()
        result = result or {}
        status_value, _method, _confidence, _note = _derive_mapping_status(result)
        existing = teacher.metadata_json if isinstance(teacher.metadata_json, dict) else {}
        teacher.metadata_json = {
            **existing,
            'cms_user': {
                'status': status_value,
                'openedx_user_id': str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None,
                'openedx_username': str(result.get('openedx_username') or result.get('username') or '').strip() or None,
                'openedx_email': str(result.get('openedx_email') or result.get('email') or '').strip() or None,
                'openedx_is_active': _boolish(result.get('openedx_is_active', result.get('is_active'))),
                'match_method': str(result.get('match_method') or '').strip() or None,
                'created': _boolish(result.get('created')),
                'note': str(result.get('note') or '')[:1000],
                'last_resolved_at': now.isoformat(),
            }
        }
        teacher.updated_at = now
        self.db.add(teacher)
        return status_value

    def resolve_class_openedx_users(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        limit = max(1, min(500, int(limit or 500)))
        query = self.db.query(AcademicStudent, OpenEdXUserMapping).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id == class_id,
        ).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = query.all()
        if not force:
            rows = [(student, mapping) for student, mapping in rows if not mapping or mapping.match_status not in {'matched'}]

        teacher_payload = self._teacher_payload_for_class(class_id)
        if not rows and not teacher_payload:
            return {'ok': True, 'class_id': class_id, 'total': 0, 'updated': 0, 'counts': {}, 'message': 'Không có sinh viên/giảng viên cần kiểm tra đồng bộ CMS', 'teachers': {'total': 0, 'updated': 0, 'counts': {}}}

        client = OpenEdXStudentInsightClient()
        batch_size = max(1, min(settings.openedx_student_insight_max_batch_size, 100))
        updated = 0
        counts: dict[str, int] = {}
        create_missing = bool(getattr(settings, 'academic_auto_create_cms_users', True))

        # Students: AP username is the canonical key. Missing CMS users are created
        # by the plugin using AP username/email/full_name when enabled.
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = [{
                'student_code': student.student_code,
                'username': normalize_username(student.username),
                'person_type': 'student',
                'role': 'student',
                'email': student.email or (f'{normalize_username(student.username)}@fpt.edu.vn' if student.username else None),
                'full_name': student.full_name,
                'create_missing': create_missing,
            } for student, _mapping in chunk]
            results = client.resolve_users(payload, create_missing=create_missing)
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
                if result.get('created') is True:
                    counts['created_user'] = counts.get('created_user', 0) + 1
                updated += 1
            self.db.flush()

        # Teachers: AP only provides values such as teacher="ngocnb61". Create
        # username/email/first_name/last_name deterministically in the plugin.
        teacher_counts: dict[str, int] = {}
        teacher_updated = 0
        if teacher_payload:
            for start in range(0, len(teacher_payload), batch_size):
                chunk = teacher_payload[start:start + batch_size]
                results = client.resolve_users([payload for _teacher, payload in chunk], create_missing=create_missing)
                result_by_username = {normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username')): item for item in results if normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username'))}
                for teacher, payload in chunk:
                    username = normalize_username(payload.get('username'))
                    result = result_by_username.get(username) or {
                        'ap_username': username,
                        'username': username,
                        'person_type': 'teacher',
                        'exists': False,
                        'match_status': 'missing',
                        'match_method': 'not_found',
                        'note': 'Open edX plugin không trả user cho giảng viên này',
                    }
                    status_value = self._upsert_teacher_cms_metadata(teacher, result)
                    teacher_counts[status_value] = teacher_counts.get(status_value, 0) + 1
                    counts[f'teacher_{status_value}'] = counts.get(f'teacher_{status_value}', 0) + 1
                    if result.get('created') is True:
                        teacher_counts['created_user'] = teacher_counts.get('created_user', 0) + 1
                        counts['teacher_created_user'] = counts.get('teacher_created_user', 0) + 1
                    teacher_updated += 1
                self.db.flush()

        self.db.commit()
        enrollment_result = None
        if getattr(settings, 'academic_auto_enroll_after_cms_sync', True):
            try:
                # Auto-enroll mapped students and add mapped/created teachers to Course Staff.
                enrollment_result = self.sync_class_course_enrollment(user, class_id, force=False, limit=limit)
                for key, value in (enrollment_result.get('counts') or {}).items():
                    counts[f'enrollment_{key}'] = int(value or 0)
            except HTTPException as exc:
                enrollment_result = {'ok': False, 'message': str(exc.detail)}
                counts['enrollment_skipped'] = counts.get('enrollment_skipped', 0) + 1
            except Exception as exc:
                enrollment_result = {'ok': False, 'message': str(exc)}
                counts['enrollment_failed'] = counts.get('enrollment_failed', 0) + 1
        message = 'Đã kiểm tra đồng bộ CMS theo AP username; tự tạo tài khoản CMS nếu chưa có dữ liệu'
        if enrollment_result:
            if enrollment_result.get('ok'):
                message += '; đã tự enroll sinh viên và gán giảng viên vào Course CMS nếu lớp đã map course'
            else:
                message += f"; chưa auto-enroll/gán giảng viên được: {enrollment_result.get('message')}"
        return {
            'ok': True,
            'class_id': class_id,
            'total': len(rows),
            'updated': updated,
            'counts': counts,
            'message': message,
            'enrollment': enrollment_result,
            'teachers': {'total': len(teacher_payload), 'updated': teacher_updated, 'counts': teacher_counts},
        }

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None or value == '':
            return None
        try:
            number = float(value)
        except Exception:
            return None
        # Plugins may return 0..1 or 0..100. Store percent in 0..100.
        if 0 <= number <= 1:
            return round(number * 100.0, 2)
        return round(number, 2)

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value is None or value == '':
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _dt_or_none(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            return None

    def _learning_summary_for_class_course(self, class_id: str, course_id: str | None) -> dict[str, Any]:
        total = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == class_id).scalar() or 0
        if not course_id:
            return {'class_id': class_id, 'openedx_course_id': None, 'total': int(total), 'counts': {'not_synced': int(total)}, 'active_count': 0, 'avg_progress_percent': None, 'avg_grade_percent': None, 'last_synced_at': None, 'component_summaries': [], 'status_counts': {'not_synced': int(total)}, 'alert_counts': {'not_synced': int(total)}}
        rows = self.db.query(AcademicStudentLearningSnapshot.enrollment_status, func.count(AcademicStudentLearningSnapshot.id)).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).group_by(AcademicStudentLearningSnapshot.enrollment_status).all()
        counts = {str(status or 'unknown'): int(count or 0) for status, count in rows}
        synced = sum(counts.values())
        counts['not_synced'] = max(0, int(total) - synced)
        avg_progress = self.db.query(func.avg(AcademicStudentLearningSnapshot.progress_percent)).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            AcademicStudentLearningSnapshot.progress_percent.isnot(None),
        ).scalar()
        avg_grade = self.db.query(func.avg(AcademicStudentLearningSnapshot.grade_percent)).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            AcademicStudentLearningSnapshot.grade_percent.isnot(None),
        ).scalar()
        last_synced = self.db.query(func.max(func.coalesce(AcademicStudentLearningSnapshot.learning_synced_at, AcademicStudentLearningSnapshot.last_synced_at))).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).scalar()
        snapshots = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).all()
        status_counts: dict[str, int] = {}
        alert_counts = {'cms_not_synced': 0, 'not_enrolled': 0, 'no_activity': 0, 'low_progress': 0, 'low_grade': 0, 'sync_error': 0, 'good': 0, 'in_progress': 0}
        active_count = sum(1 for snapshot in snapshots if self._snapshot_has_learning_activity(snapshot))
        snapshot_by_student = {snapshot.student_id: snapshot for snapshot in snapshots}
        mapping_rows = self.db.query(AcademicClassStudent.student_id, OpenEdXUserMapping).outerjoin(
            OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
        ).filter(AcademicClassStudent.class_id == class_id).all()
        for student_id, mapping in mapping_rows:
            status_name = self._learning_status_for_snapshot(snapshot_by_student.get(student_id), mapping)
            status_counts[status_name] = status_counts.get(status_name, 0) + 1
            if status_name in alert_counts:
                alert_counts[status_name] += 1
        return {
            'class_id': class_id,
            'openedx_course_id': course_id,
            'total': int(total),
            'counts': counts,
            'active_count': active_count,
            'avg_progress_percent': round(float(avg_progress), 2) if avg_progress is not None else None,
            'avg_grade_percent': round(float(avg_grade), 2) if avg_grade is not None else None,
            'last_synced_at': last_synced,
            'component_summaries': self._component_summary_from_snapshots(snapshots),
            'status_counts': status_counts,
            'alert_counts': alert_counts,
        }

    def learning_summary_for_class(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        mapping = self.effective_course_mapping_for_class(cls)
        return self._learning_summary_for_class_course(class_id, mapping.openedx_course_id if mapping else None)

    def _upsert_learning_snapshot(self, *, class_id: str, student: AcademicStudent, course_id: str, result: dict[str, Any], source: str) -> AcademicStudentLearningSnapshot:
        now = datetime.utcnow()
        snapshot = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.student_id == student.id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).first()
        if not snapshot:
            snapshot = AcademicStudentLearningSnapshot(class_id=class_id, student_id=student.id, openedx_course_id=course_id, created_at=now)
        enrollment = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
        progress = result.get('progress') if isinstance(result.get('progress'), dict) else {}
        grade = result.get('grade') if isinstance(result.get('grade'), dict) else {}
        snapshot.openedx_username = str(result.get('openedx_username') or result.get('username') or student.username or '').strip() or None
        snapshot.openedx_user_id = str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None
        snapshot.enrollment_status = str(
            result.get('enrollment_status')
            or enrollment.get('status')
            or ('enrolled' if enrollment.get('is_enrolled') is True else ('not_enrolled' if enrollment.get('is_enrolled') is False else 'unknown'))
        )[:50]
        snapshot.enrollment_mode = str(result.get('enrollment_mode') or enrollment.get('mode') or '').strip()[:50] or None
        snapshot.progress_percent = self._float_or_none(result.get('progress_percent', progress.get('percent')))
        snapshot.grade_percent = self._float_or_none(result.get('grade_percent', grade.get('percent')))
        if 'passed' in result:
            snapshot.passed = _boolish(result.get('passed'))
        elif 'passed' in grade:
            snapshot.passed = _boolish(grade.get('passed'))
        snapshot.completed_blocks = self._int_or_none(result.get('completed_blocks', progress.get('completed_blocks')))
        snapshot.total_blocks = self._int_or_none(result.get('total_blocks', progress.get('total_blocks')))
        snapshot.last_activity_at = self._dt_or_none(result.get('last_activity_at') or progress.get('last_activity_at'))
        snapshot.raw_json = {'source': source, 'payload': result}
        snapshot.learning_synced_at = now
        snapshot.last_synced_at = now
        snapshot.updated_at = now
        self.db.add(snapshot)
        return snapshot


    def _upsert_enrollment_snapshot(self, *, class_id: str, student: AcademicStudent, course_id: str, result: dict[str, Any], source: str) -> AcademicStudentLearningSnapshot:
        """Update only enrollment fields without wiping progress/grade snapshots."""
        now = datetime.utcnow()
        snapshot = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.student_id == student.id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).first()
        if not snapshot:
            snapshot = AcademicStudentLearningSnapshot(class_id=class_id, student_id=student.id, openedx_course_id=course_id, created_at=now)
        enrollment = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
        raw_status = str(result.get('enrollment_status') or enrollment.get('status') or result.get('status') or '').strip().lower()
        is_enrolled = result.get('is_enrolled')
        if is_enrolled is None:
            is_enrolled = enrollment.get('is_enrolled')
        if raw_status in {'enrolled', 'already_enrolled', 'created', 'reactivated'} or is_enrolled is True:
            status_value = 'enrolled'
        elif raw_status in {'missing_user', 'inactive_user', 'not_mapped', 'failed', 'skipped'}:
            status_value = raw_status
        elif raw_status:
            status_value = raw_status
        else:
            status_value = 'unknown'
        snapshot.openedx_username = str(result.get('openedx_username') or result.get('username') or student.username or '').strip() or snapshot.openedx_username
        snapshot.openedx_user_id = str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or snapshot.openedx_user_id
        snapshot.enrollment_status = status_value[:50]
        snapshot.enrollment_mode = str(result.get('enrollment_mode') or enrollment.get('mode') or '').strip()[:50] or snapshot.enrollment_mode
        existing_raw = snapshot.raw_json if isinstance(snapshot.raw_json, dict) else {}
        snapshot.raw_json = {**existing_raw, 'enrollment_source': source, 'enrollment_payload': result}
        snapshot.enrollment_synced_at = now
        if snapshot.last_synced_at is None:
            snapshot.last_synced_at = now
        snapshot.updated_at = now
        self.db.add(snapshot)
        return snapshot

    def sync_class_course_enrollment(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, mode: str | None = None) -> dict[str, Any]:
        """Enroll AP students and add AP teachers to the mapped CMS/Open edX course.

        Students are enrolled only after exact AP username -> CMS user mapping.
        Teachers are resolved/created from AP teacher username and granted Course
        Staff in the course. No fuzzy matching is used.
        """
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        mapping = self.effective_course_mapping_for_class(cls)
        if not mapping or not mapping.openedx_course_id:
            raise HTTPException(status_code=400, detail='Lớp chưa có Course CMS nên chưa thể tự enrollment/gán giảng viên')
        course_id = mapping.openedx_course_id
        cohort_name = self._cohort_for_class_mapping(cls, mapping) or cls.class_code
        limit = max(1, min(500, int(limit or 500)))
        query = self.db.query(AcademicStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).join(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).outerjoin(
            AcademicStudentLearningSnapshot,
            and_(
                AcademicStudentLearningSnapshot.class_id == class_id,
                AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            ),
        ).filter(
            AcademicClassStudent.class_id == class_id,
            OpenEdXUserMapping.match_status == 'matched',
            or_(OpenEdXUserMapping.openedx_is_active.is_(None), OpenEdXUserMapping.openedx_is_active.is_(True)),
            or_(OpenEdXUserMapping.openedx_username.isnot(None), OpenEdXUserMapping.openedx_user_id.isnot(None)),
        ).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = query.all()
        if not force:
            rows = [(student, mapping_row, snapshot) for student, mapping_row, snapshot in rows if not snapshot or snapshot.enrollment_status not in {'enrolled'}]

        teacher_payload = self._teacher_payload_for_class(class_id) if getattr(settings, 'academic_auto_add_teachers_to_course', True) else []
        if not rows and not teacher_payload:
            summary = self._learning_summary_for_class_course(class_id, course_id)
            return {'ok': True, 'class_id': class_id, 'openedx_course_id': course_id, 'total': 0, 'updated': 0, 'counts': {}, 'message': 'Không có sinh viên/giảng viên cần xử lý Course CMS', 'learning_summary': summary, 'teachers': {'total': 0, 'updated': 0, 'counts': {}}}
        client = OpenEdXStudentInsightClient()
        batch_size = max(1, min(settings.openedx_student_insight_max_batch_size, 100))
        counts: dict[str, int] = {}
        updated = 0
        teacher_counts: dict[str, int] = {}
        teacher_updated = 0
        enrollment_mode = (mode or getattr(settings, 'openedx_student_insight_default_enrollment_mode', 'audit') or 'audit').strip() or 'audit'
        create_missing = bool(getattr(settings, 'academic_auto_create_cms_users', True))

        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = []
            for student, mapping_row, _snapshot in chunk:
                payload.append({
                    'student_code': student.student_code,
                    'ap_username': normalize_username(student.username),
                    'username': normalize_username(mapping_row.openedx_username or student.username),
                    'openedx_user_id': mapping_row.openedx_user_id,
                    'person_type': 'student',
                    'role': 'student',
                    'email': student.email or (f'{normalize_username(student.username)}@fpt.edu.vn' if student.username else None),
                    'full_name': student.full_name,
                    'create_missing': create_missing,
                })
            results = client.enroll_users(course_id=course_id, cohort_name=cohort_name, students=payload, mode=enrollment_mode, force=force, create_missing=create_missing)
            by_username = {normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username')): item for item in results if normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username'))}
            by_code = {str(item.get('student_code') or '').strip().lower(): item for item in results if str(item.get('student_code') or '').strip()}
            for student, mapping_row, _snapshot in chunk:
                key = normalize_username(mapping_row.openedx_username or student.username)
                result = by_username.get(key) or by_username.get(normalize_username(student.username))
                if result is None and student.student_code:
                    result = by_code.get(str(student.student_code).strip().lower())
                if result is None:
                    result = {
                        'student_code': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': key,
                        'enrollment_status': 'unknown',
                        'message': 'Plugin không trả kết quả enrollment cho sinh viên này',
                    }
                snapshot = self._upsert_enrollment_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_student_insight_enrollment')
                status_value = str(result.get('status') or result.get('enrollment_status') or snapshot.enrollment_status or 'unknown')
                if status_value in {'already_enrolled', 'created', 'reactivated'}:
                    status_value = 'enrolled'
                counts[status_value] = counts.get(status_value, 0) + 1
                updated += 1
            self.db.flush()

        # Add teachers to Course Staff. Teachers are not stored in student learning
        # snapshots; their status is kept in academic_teachers.metadata_json.
        if teacher_payload:
            for start in range(0, len(teacher_payload), batch_size):
                chunk = teacher_payload[start:start + batch_size]
                teacher_items = [payload for _teacher, payload in chunk]
                results = client.enroll_users(course_id=course_id, cohort_name=cohort_name, students=[], teachers=teacher_items, mode=enrollment_mode, force=force, create_missing=create_missing)
                result_by_username = {normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username')): item for item in results if normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username'))}
                for teacher, payload in chunk:
                    username = normalize_username(payload.get('username'))
                    result = result_by_username.get(username) or {'username': username, 'status': 'unknown', 'message': 'Plugin không trả kết quả gán giảng viên'}
                    existing = teacher.metadata_json if isinstance(teacher.metadata_json, dict) else {}
                    teacher.metadata_json = {
                        **existing,
                        'course_staff': {
                            'openedx_course_id': course_id,
                            'status': str(result.get('status') or result.get('enrollment_status') or 'unknown'),
                            'openedx_user_id': str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None,
                            'openedx_username': str(result.get('openedx_username') or result.get('username') or '').strip() or None,
                            'openedx_email': str(result.get('openedx_email') or result.get('email') or '').strip() or None,
                            'created_user': _boolish(result.get('created_user', result.get('created'))),
                            'message': str(result.get('message') or '')[:1000],
                            'last_synced_at': datetime.utcnow().isoformat(),
                        }
                    }
                    teacher.updated_at = datetime.utcnow()
                    self.db.add(teacher)
                    status_value = str(result.get('status') or result.get('enrollment_status') or 'unknown')
                    teacher_counts[status_value] = teacher_counts.get(status_value, 0) + 1
                    counts[f'teacher_{status_value}'] = counts.get(f'teacher_{status_value}', 0) + 1
                    teacher_updated += 1
                self.db.flush()

        self.db.commit()
        summary = self._learning_summary_for_class_course(class_id, course_id)
        return {
            'ok': True,
            'class_id': class_id,
            'openedx_course_id': course_id,
            'total': len(rows),
            'updated': updated,
            'counts': counts,
            'message': 'Đã tự enrollment sinh viên đã đồng bộ CMS và gán giảng viên vào Course CMS',
            'learning_summary': summary,
            'teachers': {'total': len(teacher_payload), 'updated': teacher_updated, 'counts': teacher_counts},
        }

    def sync_class_learning_insight(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        mapping = self.effective_course_mapping_for_class(cls)
        if not mapping or not mapping.openedx_course_id:
            raise HTTPException(status_code=400, detail='Lớp chưa có Course CMS. Hãy map Course CMS trước khi cập nhật tiến độ/điểm.')
        course_id = mapping.openedx_course_id
        cohort_name = self._cohort_for_class_mapping(cls, mapping) or cls.class_code
        limit = max(1, min(500, int(limit or 500)))
        if getattr(settings, 'academic_auto_enroll_after_cms_sync', True):
            try:
                self.sync_class_course_enrollment(user, class_id, force=False, limit=limit)
            except HTTPException as exc:
                # Missing course mapping is already handled above; enrollment plugin
                # failures should not block a read-only progress/grade refresh.
                if exc.status_code >= 500:
                    raise
            except Exception:
                pass
        query = self.db.query(AcademicStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).outerjoin(
            AcademicStudentLearningSnapshot,
            and_(
                AcademicStudentLearningSnapshot.class_id == class_id,
                AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            ),
        ).filter(AcademicClassStudent.class_id == class_id).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = query.all()
        if not force:
            rows = [(student, mapping_row, snapshot) for student, mapping_row, snapshot in rows if not self._snapshot_has_learning_payload(snapshot)]
        if not rows:
            summary = self._learning_summary_for_class_course(class_id, course_id)
            return {'ok': True, 'updated': 0, 'message': 'Không có sinh viên cần cập nhật học tập CMS', **summary}
        client = OpenEdXStudentInsightClient()
        batch_size = max(1, min(settings.openedx_student_insight_max_batch_size, 100))
        updated = 0
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = []
            for student, mapping_row, _snapshot in chunk:
                payload.append({
                    'student_code': student.student_code,
                    'username': normalize_username((mapping_row.openedx_username if mapping_row and mapping_row.openedx_username else student.username)),
                    'ap_username': normalize_username(student.username),
                    'openedx_user_id': mapping_row.openedx_user_id if mapping_row else None,
                    'email': student.email,
                    'full_name': student.full_name,
                })
            results = client.class_analytics(course_id=course_id, cohort_name=cohort_name, students=payload)
            by_username = {normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username')): item for item in results if normalize_username(item.get('ap_username') or item.get('username') or item.get('openedx_username'))}
            by_code = {str(item.get('student_code') or '').strip().lower(): item for item in results if str(item.get('student_code') or '').strip()}
            for student, mapping_row, _snapshot in chunk:
                key = normalize_username(mapping_row.openedx_username if mapping_row and mapping_row.openedx_username else student.username)
                result = by_username.get(key) or by_username.get(normalize_username(student.username))
                if result is None and student.student_code:
                    result = by_code.get(str(student.student_code).strip().lower())
                if result is None:
                    result = {
                        'student_code': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': key,
                        'enrollment_status': 'unknown',
                        'note': 'Plugin không trả dữ liệu học tập cho sinh viên này',
                    }
                self._upsert_learning_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_student_insight')
                updated += 1
            self.db.flush()
        self.db.commit()
        summary = self._learning_summary_for_class_course(class_id, course_id)
        return {'ok': True, 'updated': updated, 'message': 'Đã cập nhật tiến độ/điểm CMS cho lớp', **summary}


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

