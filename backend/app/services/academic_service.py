from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from uuid import UUID
from typing import Any
from zoneinfo import ZoneInfo

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
from app.services.openedx_student_insight import OpenEdXConnectorClient, normalize_username, mask_email
from app.services.training_policy_service import TrainingPolicyService
from app.core.config import settings
from app.models.course import CourseSyncState
from app.models.question_bank import Subject as BankSubject


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

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


def _natural_sort_key(value: Any) -> list[Any]:
    raw = str(value or '').strip().lower()
    parts = re.split(r'(\d+)', raw)
    return [int(part) if part.isdigit() else part for part in parts]


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

def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_mapping_raw(result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    safe: dict[str, Any] = {}
    for key, value in result.items():
        if key in {'email', 'openedx_email', 'ap_email'}:
            safe[key] = mask_email(value)
        elif key in {'full_name', 'name', 'phone'}:
            safe[key] = '***REDACTED***'
        else:
            safe[key] = _json_safe_value(value)
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

    def _payload_from_snapshot(self, snapshot: AcademicStudentLearningSnapshot | None) -> dict[str, Any]:
        if not snapshot or not isinstance(snapshot.raw_json, dict):
            return {}
        raw = snapshot.raw_json
        payload = raw.get('payload') if isinstance(raw.get('payload'), dict) else {}
        # Some older jobs wrote partial data under enrollment_payload/learning_payload
        # or stored the connector result directly at raw_json root. Merge, do not
        # overwrite the main learning payload. This makes old snapshots readable
        # after a code upgrade without forcing a destructive resync.
        merged: dict[str, Any] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key not in {'payload'}:
                    merged[key] = value
        if isinstance(raw.get('enrollment_payload'), dict):
            merged.setdefault('enrollment_payload', raw.get('enrollment_payload'))
        if isinstance(raw.get('learning_payload'), dict):
            merged.update(raw.get('learning_payload') or {})
        if isinstance(payload, dict):
            merged.update(payload)
        return merged

    def _percent_from_value(self, value: Any, *, kind: str = 'progress') -> float | None:
        if isinstance(value, dict):
            direct_keys = (
                'percent', 'percentage', 'value', 'score_percent', 'grade_percent',
                'progress_percent', 'course_progress_percent', 'completion_percent',
                'course_completion_percent', 'courseCompletionPercent', 'completed_percent',
                'percent_complete', 'percentComplete', 'completion_rate', 'completionRate',
                'completion', 'course_completion', 'courseCompletion', 'progress',
            )
            for key in direct_keys:
                if key in value:
                    percent = self._percent_display_value(value.get(key))
                    if percent is not None:
                        return percent
            completed = self._number_or_none(
                value.get('completed_blocks')
                or value.get('complete_count')
                or value.get('completed_count')
                or value.get('completed')
                or value.get('complete')
                or value.get('done')
                or value.get('visited')
            )
            total = self._number_or_none(
                value.get('total_blocks')
                or value.get('total_count')
                or value.get('block_count')
                or value.get('total')
                or value.get('possible')
                or value.get('required')
            )
            if completed is not None and total and total > 0:
                return round((completed / total) * 100.0, 2)
            return None
        return self._percent_display_value(value)

    def _candidate_payload_containers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        containers: list[dict[str, Any]] = []
        seen: set[int] = set()

        def add(value: Any, depth: int = 0) -> None:
            if depth > 2 or not isinstance(value, dict):
                return
            marker = id(value)
            if marker in seen:
                return
            seen.add(marker)
            containers.append(value)
            for key in (
                'payload', 'result', 'data', 'analytics', 'course', 'courseware',
                'progress', 'course_progress', 'courseProgress', 'completion',
                'course_completion', 'courseCompletion', 'completion_summary',
                'completionSummary', 'progress_summary', 'progressSummary',
                'grade', 'grades', 'overall', 'summary', 'student', 'learner',
                'details', 'detail', 'detailed', 'gradebook', 'grading',
            ):
                child = value.get(key)
                if isinstance(child, dict):
                    add(child, depth + 1)

        add(payload)
        return containers

    def _progress_percent_from_payload(self, payload: dict[str, Any]) -> float | None:
        if not isinstance(payload, dict):
            return None
        keys = (
            'progress_percent', 'course_progress_percent', 'completion_percent',
            'course_completion_percent', 'courseCompletionPercent', 'completed_percent',
            'percent_complete', 'percentComplete', 'completion_rate', 'completionRate',
            'progress', 'course_progress', 'courseProgress', 'completion',
            'course_completion', 'courseCompletion', 'completion_summary',
            'completionSummary', 'progress_summary', 'progressSummary', 'progressSummaryData',
        )
        for container in self._candidate_payload_containers(payload):
            for key in keys:
                if key not in container:
                    continue
                percent = self._percent_from_value(container.get(key), kind='progress')
                if percent is not None:
                    return percent
            completed = self._number_or_none(container.get('completed_blocks') or container.get('completed_count') or container.get('completed') or container.get('done') or container.get('visited'))
            total = self._number_or_none(container.get('total_blocks') or container.get('total_count') or container.get('block_count') or container.get('total') or container.get('required'))
            if completed is not None and total and total > 0:
                return round((completed / total) * 100.0, 2)
        # Do not infer Course completion from grade/quiz components.
        # Course completion is a distinct CMS/Open edX progress value. If the
        # connector does not return an official progress/completion percentage,
        # show N/A rather than a misleading ratio of completed quizzes.
        return None

    def _grade_percent_from_payload(self, payload: dict[str, Any]) -> float | None:
        if not isinstance(payload, dict):
            return None
        keys = (
            'grade_percent', 'total_grade_percent', 'overall_grade_percent',
            'course_grade_percent', 'percent_graded', 'weighted_percent',
            'grade', 'total_grade', 'overall_grade', 'course_grade',
            'final_grade', 'grading', 'grade_summary', 'gradeSummary',
        )
        for container in self._candidate_payload_containers(payload):
            for key in keys:
                if key not in container:
                    continue
                percent = self._percent_from_value(container.get(key), kind='grade')
                if percent is not None:
                    return percent
        return None

    def _snapshot_progress_percent(self, snapshot: AcademicStudentLearningSnapshot | None) -> float | None:
        if not snapshot:
            return None
        payload = self._payload_from_snapshot(snapshot)
        progress_payload = payload.get('progress') if isinstance(payload.get('progress'), dict) else {}
        progress_source = str(progress_payload.get('source') or payload.get('progress_source') or payload.get('progressSource') or '').strip().lower()
        # Old connector fallbacks based on StudentModule/BlockCompletion can disagree
        # with the official CMS learner Course completion. Do not reuse those
        # values as Course completion; the UI should show N/A unless the connector
        # returns an official Course Home/progress completion value.
        fallback_sources = {'studentmodule', 'student_module', 'blockcompletion', 'block_completion'}
        if progress_source and progress_source.replace(' ', '').lower() not in fallback_sources:
            direct = self._percent_display_value(snapshot.progress_percent)
            if direct is not None:
                return direct
        if not progress_source:
            direct = self._percent_display_value(snapshot.progress_percent)
            if direct is not None:
                return direct
        return self._progress_percent_from_payload(payload)

    def _snapshot_grade_percent(self, snapshot: AcademicStudentLearningSnapshot | None) -> float | None:
        if not snapshot:
            return None
        direct = self._percent_display_value(snapshot.grade_percent)
        if direct is not None:
            return direct
        return self._grade_percent_from_payload(self._payload_from_snapshot(snapshot))

    def _normalize_component_score_item(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        key = str(
            item.get('key')
            or item.get('usage_key')
            or item.get('usageKey')
            or item.get('block_id')
            or item.get('blockId')
            or item.get('module_id')
            or item.get('moduleId')
            or item.get('id')
            or item.get('name')
            or item.get('display_name')
            or item.get('displayName')
            or item.get('label')
            or item.get('title')
            or ''
        ).strip()
        name = str(
            item.get('name')
            or item.get('display_name')
            or item.get('displayName')
            or item.get('subsection_name')
            or item.get('subsectionName')
            or item.get('assignment_name')
            or item.get('assignmentName')
            or item.get('label')
            or item.get('title')
            or item.get('module_name')
            or item.get('moduleName')
            or key
            or 'Điểm thành phần'
        ).strip()
        earned = self._number_or_none(
            item.get('earned', item.get('earned_graded', item.get('earnedGraded', item.get('earned_score', item.get('earnedScore', item.get('score_earned', item.get('scoreEarned', item.get('score', item.get('points_earned')))))))))
        )
        possible = self._number_or_none(
            item.get('possible', item.get('possible_graded', item.get('possibleGraded', item.get('possible_score', item.get('possibleScore', item.get('score_possible', item.get('scorePossible', item.get('max_score', item.get('maxScore', item.get('max_grade', item.get('points_possible')))))))))))
        )
        percent = self._percent_display_value(
            item.get('percent', item.get('percentage', item.get('grade_percent', item.get('gradePercent', item.get('score_percent', item.get('scorePercent', item.get('percent_graded', item.get('percentGraded', item.get('value')))))))))
        )
        if percent is None and earned is not None and possible and possible > 0:
            percent = round((earned / possible) * 100.0, 2)
        planned = bool(item.get('planned') is True or item.get('is_planned') is True or str(item.get('source') or '').strip().lower() in {'course_outline', 'cms_course_outline'})
        if percent is None and earned is None and possible is None and not planned:
            return None
        submitted_at = item.get('submitted_at') or item.get('submittedAt') or item.get('last_submitted_at') or item.get('lastSubmittedAt') or item.get('attempted_at') or item.get('attemptedAt') or item.get('modified') or item.get('updated_at') or item.get('updatedAt')
        available_from = item.get('available_from') or item.get('availableFrom') or item.get('start_date') or item.get('startDate') or item.get('open_date') or item.get('openDate')
        deadline_date = item.get('deadline_date') or item.get('deadlineDate') or item.get('deadline') or item.get('due_date') or item.get('dueDate') or item.get('due')
        quiz_numbers = self._quiz_numbers_from_text(' '.join([str(name or ''), str(key or ''), str(item.get('category') or '')]))
        quiz_number = quiz_numbers[0] if quiz_numbers else None
        return {
            'key': key or name,
            'name': name[:255],
            'category': str(item.get('category') or item.get('type') or item.get('format') or item.get('block_type') or '').strip() or None,
            'earned': round(earned, 2) if earned is not None else None,
            'possible': round(possible, 2) if possible is not None else None,
            'percent': percent,
            'weight': self._number_or_none(item.get('weight')),
            'source': str(item.get('source') or item.get('model') or '').strip() or None,
            'planned': planned,
            'order': int(self._number_or_none(item.get('order') or item.get('index') or item.get('position') or item.get('quiz_index') or item.get('quizIndex')) or 0) or None,
            'quiz_number': quiz_number,
            'submitted_at': submitted_at,
            'available_from': available_from,
            'deadline_date': deadline_date,
        }

    def _component_scores_from_payload(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        component_keys = (
            'detailed_grades',
            'detailedGrades',
            'detailed_grade',
            'detailed_grade_breakdown',
            'detailedGradeBreakdown',
            'grade_breakdown',
            'gradeBreakdown',
            'grade_details',
            'gradeDetails',
            'component_scores',
            'componentScores',
            'component_grades',
            'componentGrades',
            'grade_components',
            'gradeComponents',
            'graded_subsections',
            'gradedSubsections',
            'subsection_grades',
            'subsectionGrades',
            'section_scores',
            'sectionScores',
            'scores',
            'items',
            'results',
            'rows',
            'breakdown',
            'components',
            'subsections',
            'assignments',
            'detailed',
            'details',
        )
        candidate_lists: list[Any] = []
        for container in self._candidate_payload_containers(payload):
            for key in component_keys:
                candidate_lists.append(container.get(key))
            grade = container.get('grade') if isinstance(container.get('grade'), dict) else {}
            for key in component_keys:
                candidate_lists.append(grade.get(key))
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidate_lists:
            if isinstance(candidate, dict):
                # Candidate may be either a single component object or a mapping
                # {component_name: score}. Try single object first.
                single = self._normalize_component_score_item(candidate)
                if single:
                    candidate = [candidate]
                else:
                    iterable = []
                    for key, value in candidate.items():
                        if isinstance(value, dict):
                            iterable.append({'key': key, 'name': value.get('name') or value.get('display_name') or value.get('displayName') or key, **value})
                        elif isinstance(value, list):
                            for sub in value:
                                if isinstance(sub, dict):
                                    iterable.append({'parent_key': key, **sub})
                        elif isinstance(value, (int, float, str)):
                            iterable.append({'key': key, 'name': key, 'percent': value})
                    candidate = iterable
            if not isinstance(candidate, list):
                continue
            for raw_item in candidate:
                item = self._normalize_component_score_item(raw_item)
                if not item:
                    continue
                identity = self._component_identity_key(item)
                if identity in seen:
                    # Prefer the item that has actual score data over a planned shell.
                    for index, existing in enumerate(normalized):
                        if self._component_identity_key(existing) != identity:
                            continue
                        existing_has_score = self._number_or_none(existing.get('percent')) is not None or self._number_or_none(existing.get('earned')) is not None
                        item_has_score = self._number_or_none(item.get('percent')) is not None or self._number_or_none(item.get('earned')) is not None
                        if item_has_score and not existing_has_score:
                            normalized[index] = item
                        break
                    continue
                seen.add(identity)
                normalized.append(item)
        # If CMS returned real Detailed grades for Quiz 1..N, do not keep
        # course-outline planned quiz shells beyond that range. This prevents
        # duplicate/phantom columns such as Quiz 2 twice or Quiz 14 when the CMS
        # gradebook currently has only Quiz 1 and Quiz 2.
        real_quiz_numbers = [int(item.get('quiz_number') or 0) for item in normalized if item.get('quiz_number') and not item.get('planned')]
        if real_quiz_numbers:
            max_real_quiz = max(real_quiz_numbers)
            normalized = [item for item in normalized if not (item.get('planned') and item.get('quiz_number') and int(item.get('quiz_number') or 0) > max_real_quiz)]
        normalized.sort(key=lambda item: self._component_sort_key(item))
        return normalized[:80]


    def _component_identity_key(self, item: dict[str, Any] | None) -> str:
        if not isinstance(item, dict):
            return ''
        numbers = self._quiz_numbers_from_component_item(item)
        if numbers:
            return f"quiz:{numbers[0]}"
        raw = item.get('key') or item.get('usage_key') or item.get('name') or ''
        return _normalize_text_key(raw)

    def _component_sort_key(self, item: dict[str, Any]) -> tuple[int, int, Any]:
        numbers = self._quiz_numbers_from_component_item(item)
        if numbers:
            return (0, int(numbers[0]), _natural_sort_key(item.get('name') or item.get('key') or ''))
        order = self._number_or_none(item.get('order'))
        if order is not None and order > 0:
            return (1, int(order), _natural_sort_key(item.get('name') or item.get('key') or ''))
        return (2, 9999, _natural_sort_key(item.get('name') or item.get('key') or ''))

    def _component_scores_from_snapshot(self, snapshot: AcademicStudentLearningSnapshot | None) -> list[dict[str, Any]]:
        if not snapshot or not isinstance(snapshot.raw_json, dict):
            return []
        # Use the merged snapshot payload so component grades are still readable
        # when enrollment sync later wrote enrollment_payload next to the original
        # class-analytics payload, or when older jobs stored connector results at
        # raw_json root.
        return self._component_scores_from_payload(self._payload_from_snapshot(snapshot))

    @staticmethod
    def _date_only(value: Any) -> date | None:
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(VN_TZ).date()
            return value.date()
        if isinstance(value, date):
            return value
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(VN_TZ)
            return parsed.date()
        except Exception:
            pass
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _quiz_numbers_from_text(value: Any) -> list[int]:
        raw = str(value or '').strip().lower()
        if not raw:
            return []
        numbers: set[int] = set()
        for start, end in re.findall(r'quiz\s*#?\s*(\d{1,3})\s*[-–]\s*(\d{1,3})', raw, flags=re.I):
            a, b = int(start), int(end)
            if 1 <= a <= b <= 200:
                numbers.update(range(a, b + 1))
        for token in re.findall(r'quiz\s*#?\s*(\d{1,3})', raw, flags=re.I):
            n = int(token)
            if 1 <= n <= 200:
                numbers.add(n)
        # Some Open edX/connector payloads use labels such as "LC 1" or "Learning Check 1".
        for token in re.findall(r'(?:learning\s*check|lc)\s*#?\s*(\d{1,3})', raw, flags=re.I):
            n = int(token)
            if 1 <= n <= 200:
                numbers.add(n)
        return sorted(numbers)

    def _completed_quiz_numbers_from_snapshot(self, snapshot: AcademicStudentLearningSnapshot | None) -> set[int]:
        completed: set[int] = set()
        for item in self._component_scores_from_snapshot(snapshot):
            numbers = self._quiz_numbers_from_component_item(item)
            if not numbers:
                continue
            percent = self._number_or_none(item.get('percent'))
            earned = self._number_or_none(item.get('earned'))
            possible = self._number_or_none(item.get('possible'))
            # Deadline warning is about "đã làm quiz". In connector payloads a missing
            # component usually means no attempt. A scored component with positive score is
            # certainly completed; zero-score components remain a warning unless the plugin
            # later provides explicit attempt/completion flags.
            done = (percent is not None and percent > 0) or (earned is not None and earned > 0)
            if done or (percent is not None and possible is not None and possible == 0):
                completed.update(numbers)
        return completed

    def _quiz_numbers_from_component_item(self, item: dict[str, Any] | None) -> list[int]:
        if not isinstance(item, dict):
            return []
        text = ' '.join(str(item.get(key) or '') for key in ('name', 'key', 'category'))
        numbers = self._quiz_numbers_from_text(text)
        if numbers:
            return numbers
        category = str(item.get('category') or '').strip().lower()
        source = str(item.get('source') or '').strip().lower()
        name = str(item.get('name') or item.get('key') or '').strip().lower()
        looks_like_quiz = (
            'quiz' in category
            or 'quiz' in name
            or 'learning check' in name
            or name.startswith('lc ')
        )
        if not looks_like_quiz:
            return []
        order = self._number_or_none(item.get('order') or item.get('quiz_index') or item.get('quizIndex') or item.get('position') or item.get('index'))
        if order is not None and 1 <= int(order) <= 200:
            return [int(order)]
        return []

    @staticmethod
    def _quiz_deadline_schedule(quiz_count: int, block_start: date | None) -> list[dict[str, Any]]:
        quiz_count = max(0, int(quiz_count or 0))
        if quiz_count <= 0 or not block_start:
            return []
        # Một block học 7 tuần: 6 tuần đầu dành deadline quiz, tuần 7 là Ôn+Thi.
        quiz_weeks = 6
        base = quiz_count // quiz_weeks
        remainder = quiz_count % quiz_weeks
        schedule: list[dict[str, Any]] = []
        quiz_number = 1
        for week_index in range(quiz_weeks):
            week_quiz_count = base + (1 if week_index < remainder else 0)
            if week_quiz_count <= 0:
                continue
            from_date = block_start + timedelta(days=week_index * 7)
            due_date = from_date + timedelta(days=5)  # T2 -> T7
            quiz_numbers = list(range(quiz_number, quiz_number + week_quiz_count))
            quiz_number += week_quiz_count
            if len(quiz_numbers) == 1:
                label = f"Quiz {quiz_numbers[0]}"
            else:
                label = f"Quiz {quiz_numbers[0]}-{quiz_numbers[-1]}"
            schedule.append({
                'week_number': week_index + 1,
                'label': label,
                'quiz_numbers': quiz_numbers,
                'from_date': from_date.isoformat(),
                'due_date': due_date.isoformat(),
            })
        return schedule


    def _block_for_class(self, cls: AcademicClass | None) -> AcademicBlock | None:
        if not cls or not cls.block_id:
            return None
        try:
            return self.db.get(AcademicBlock, cls.block_id)
        except Exception:
            return None

    def _quiz_schedule_map_for_class(self, cls: AcademicClass | None, components: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        if not cls:
            return {}
        quiz_numbers: set[int] = set()
        for item in components:
            quiz_numbers.update(self._quiz_numbers_from_component_item(item))
        if not quiz_numbers:
            return {}
        block = self._block_for_class(cls)
        start_date = self._date_only(block.start_date if block else None) or self._date_only(cls.start_date)
        end_date = self._date_only(block.end_date if block else None) or self._date_only(cls.end_date)
        quiz_count = max(quiz_numbers)
        schedule_items = self._quiz_deadline_schedule(quiz_count, start_date)
        manual_required = False
        schedule_warning = None
        if not start_date or not end_date:
            manual_required = True
            schedule_warning = 'Thiếu ngày bắt đầu/kết thúc block hoặc lớp. Cần cấu hình deadline thủ công.'
        elif (end_date - start_date).days + 1 > 49:
            manual_required = True
            schedule_warning = 'Block dài hơn 7 tuần. Cần cấu hình deadline thủ công để xét trễ hạn chính xác.'
        elif start_date.weekday() != 0:
            manual_required = True
            schedule_warning = 'Ngày bắt đầu block/lớp không phải Thứ 2. Cần cấu hình deadline thủ công.'
        schedule_by_number: dict[int, dict[str, Any]] = {}
        for item in schedule_items:
            for number in item.get('quiz_numbers') or []:
                schedule_by_number[int(number)] = {
                    **item,
                    'deadline_mode': 'manual_required' if manual_required else 'auto',
                    'schedule_warning': schedule_warning if manual_required else None,
                }
        return schedule_by_number

    def _component_score_percent(self, item: dict[str, Any]) -> float | None:
        percent = self._number_or_none(item.get('percent'))
        if percent is not None:
            if 0 <= percent <= 1:
                percent *= 100.0
            return max(0.0, min(100.0, percent))
        earned = self._number_or_none(item.get('earned'))
        possible = self._number_or_none(item.get('possible'))
        if earned is not None and possible and possible > 0:
            return max(0.0, min(100.0, (earned / possible) * 100.0))
        return None

    def _component_status_for_class(self, item: dict[str, Any], cls: AcademicClass | None, schedule_by_number: dict[int, dict[str, Any]]) -> str | None:
        numbers = self._quiz_numbers_from_component_item(item)
        if not numbers:
            return None
        number = numbers[0]
        schedule = schedule_by_number.get(number) or {}
        deadline = self._date_only(item.get('deadline_date')) or self._date_only(schedule.get('due_date'))
        available_from = self._date_only(item.get('available_from')) or self._date_only(schedule.get('from_date'))
        if available_from is None and cls is not None:
            block = self._block_for_class(cls)
            available_from = self._date_only(block.start_date if block else None) or self._date_only(cls.start_date)
        submitted = self._date_only(item.get('submitted_at'))
        percent = self._component_score_percent(item)
        has_score = percent is not None
        if submitted and available_from and submitted < available_from:
            return 'early_before_start'
        if submitted and deadline and submitted > deadline:
            return 'late'
        if not has_score:
            if deadline and date.today() > deadline:
                return 'late'
            return 'not_attempted'
        if percent is not None and percent >= 100:
            return 'on_time'
        if deadline and date.today() > deadline:
            return 'late_not_100'
        return 'not_100'

    def _enrich_component_scores_for_class(self, items: list[dict[str, Any]], cls: AcademicClass | None) -> list[dict[str, Any]]:
        normalized = list(items or [])
        schedule_by_number = self._quiz_schedule_map_for_class(cls, normalized)
        enriched: list[dict[str, Any]] = []
        for item in normalized:
            row = dict(item)
            numbers = self._quiz_numbers_from_component_item(row)
            if numbers:
                number = numbers[0]
                row['quiz_number'] = number
                schedule = schedule_by_number.get(number) or {}
                if not row.get('deadline_date') and schedule.get('due_date'):
                    row['deadline_date'] = schedule.get('due_date')
                if not row.get('available_from') and schedule.get('from_date'):
                    row['available_from'] = schedule.get('from_date')
                if schedule.get('deadline_mode'):
                    row['deadline_mode'] = schedule.get('deadline_mode')
                if schedule.get('schedule_warning'):
                    row['schedule_warning'] = schedule.get('schedule_warning')
                row['quiz_status'] = self._component_status_for_class(row, cls, schedule_by_number)
            enriched.append(row)
        enriched.sort(key=lambda item: self._component_sort_key(item))
        return enriched

    def _training_deadline_status_by_class(
        self,
        class_by_id: dict[str, AcademicClass],
        block_by_class: dict[str, AcademicBlock | None],
        snapshot_by_class_student: dict[tuple[str, str], AcademicStudentLearningSnapshot],
    ) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        today = date.today()
        snapshots_by_class: dict[str, list[AcademicStudentLearningSnapshot]] = {}
        for (class_id, _student_id), snapshot in snapshot_by_class_student.items():
            snapshots_by_class.setdefault(class_id, []).append(snapshot)

        summary_by_class: dict[str, dict[str, Any]] = {}
        student_status_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for class_id, cls in class_by_id.items():
            snapshots = snapshots_by_class.get(class_id, [])
            quiz_count = 0
            quiz_component_count = 0
            for snapshot in snapshots:
                for item in self._component_scores_from_snapshot(snapshot):
                    numbers = self._quiz_numbers_from_component_item(item)
                    if numbers:
                        quiz_count = max(quiz_count, max(numbers))
                    else:
                        category = str(item.get('category') or '').strip().lower()
                        name = str(item.get('name') or item.get('key') or '').strip().lower()
                        source = str(item.get('source') or '').strip().lower()
                        if 'quiz' in category or 'quiz' in name or 'learning check' in name or name.startswith('lc '):
                            quiz_component_count += 1
            if quiz_count <= 0 and quiz_component_count > 0:
                quiz_count = quiz_component_count
            block = block_by_class.get(class_id)
            block_start = self._date_only(block.start_date if block else None) or self._date_only(cls.start_date)
            schedule = self._quiz_deadline_schedule(quiz_count, block_start)
            due_numbers: set[int] = set()
            next_item: dict[str, Any] | None = None
            for item in schedule:
                due = date.fromisoformat(str(item['due_date']))
                if today > due:
                    due_numbers.update(int(n) for n in item.get('quiz_numbers') or [])
                elif next_item is None:
                    next_item = item
            late_student_count = 0
            late_quiz_count = 0
            completed_due_sum = 0
            for (sid_class_id, student_id), snapshot in snapshot_by_class_student.items():
                if sid_class_id != class_id:
                    continue
                completed = self._completed_quiz_numbers_from_snapshot(snapshot)
                late_numbers = sorted(due_numbers - completed)
                completed_due = len(due_numbers.intersection(completed))
                completed_due_sum += completed_due
                if late_numbers:
                    late_student_count += 1
                    late_quiz_count += len(late_numbers)
                student_status_by_key[(class_id, student_id)] = {
                    'quiz_count': quiz_count,
                    'due_quiz_count': len(due_numbers),
                    'completed_due_quiz_count': completed_due,
                    'late_quiz_count': len(late_numbers),
                    'late_quizzes': [f'Quiz {n}' for n in late_numbers[:30]],
                    'next_quiz_label': next_item.get('label') if next_item else None,
                    'next_quiz_from_date': next_item.get('from_date') if next_item else None,
                    'next_quiz_due_date': next_item.get('due_date') if next_item else None,
                }
            summary_by_class[class_id] = {
                'quiz_count': quiz_count,
                'due_quiz_count': len(due_numbers),
                'completed_due_quiz_count': completed_due_sum,
                'late_student_count': late_student_count,
                'late_quiz_count': late_quiz_count,
                'next_quiz_label': next_item.get('label') if next_item else None,
                'next_quiz_from_date': next_item.get('from_date') if next_item else None,
                'next_quiz_due_date': next_item.get('due_date') if next_item else None,
                'schedule': schedule,
                'schedule_note': '6 tuần đầu của block chia deadline quiz; tuần 7 là Ôn+Thi. Quiz dư được dồn vào các tuần đầu.',
            }
        return summary_by_class, student_status_by_key

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
    def _metadata_total_relearn(*values: Any) -> int:
        for value in values:
            if not isinstance(value, dict):
                continue
            for key in ('total_relearn', 'totalRelearn', 'relearn_count', 'relearnCount', 'so_lan_hoc_lai'):
                if key in value and value.get(key) not in (None, ''):
                    try:
                        return max(0, int(float(value.get(key))))
                    except Exception:
                        return 0
        return 0

    def _quiz_count_from_metadata(self, *values: Any) -> int:
        # Deprecated: AP sync does not provide quiz plan/deadline metadata in production.
        # Quiz columns and deadline counts must come from CMS/Open edX Detailed grades
        # or the CMS course outline returned by the connector plugin.
        return 0

    def _planned_quiz_components_for_class(self, cls: AcademicClass | None) -> list[dict[str, Any]]:
        # Do not synthesize Quiz columns from AP metadata. If CMS/Open edX does not
        # return Detailed grades/course-outline components, the UI must honestly show
        # that no CMS grade components were received yet.
        return []

    def _snapshot_has_learning_activity(self, snapshot: AcademicStudentLearningSnapshot | None) -> bool:
        if not snapshot:
            return False
        if str(snapshot.enrollment_status or '').lower() != 'enrolled':
            return False
        progress = self._snapshot_progress_percent(snapshot)
        grade = self._snapshot_grade_percent(snapshot)
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
        progress = self._snapshot_progress_percent(snapshot)
        grade = self._snapshot_grade_percent(snapshot)
        if not self._snapshot_has_learning_activity(snapshot):
            return 'no_activity'
        if grade is not None and grade < self._low_grade_threshold():
            return 'low_grade'
        if progress is not None and progress < self._low_progress_threshold():
            return 'low_progress'
        if snapshot.passed is True or (grade is not None and grade >= 80) or (progress is not None and progress >= 80):
            return 'good'
        return 'in_progress'

    def _component_summary_from_snapshots(self, snapshots: list[AcademicStudentLearningSnapshot], cls: AcademicClass | None = None) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            for item in self._component_scores_from_snapshot(snapshot):
                identity = self._component_identity_key(item)
                if not identity:
                    continue
                bucket = buckets.setdefault(identity, {
                    'key': item.get('key') or item.get('name') or identity,
                    'name': item.get('name') or item.get('key') or identity,
                    'category': item.get('category'),
                    'percents': [],
                    'earned': 0.0,
                    'possible': 0.0,
                    'student_count': 0,
                    'source': item.get('source'),
                    'planned': bool(item.get('planned')),
                    'quiz_number': item.get('quiz_number'),
                    'deadline_date': item.get('deadline_date'),
                    'available_from': item.get('available_from'),
                })
                # Prefer stable CMS key/name from scored rows over planned shells.
                has_score = self._number_or_none(item.get('percent')) is not None or self._number_or_none(item.get('earned')) is not None
                if has_score:
                    bucket['key'] = item.get('key') or bucket['key']
                    bucket['name'] = item.get('name') or bucket['name']
                    bucket['category'] = item.get('category') or bucket.get('category')
                    bucket['planned'] = False
                    bucket['source'] = item.get('source') or bucket.get('source')
                if item.get('quiz_number'):
                    bucket['quiz_number'] = item.get('quiz_number')
                if item.get('deadline_date'):
                    bucket['deadline_date'] = item.get('deadline_date')
                if item.get('available_from'):
                    bucket['available_from'] = item.get('available_from')
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
                'source': bucket.get('source') or f"{bucket.get('student_count', 0)} SV",
                'planned': bool(bucket.get('planned')),
                'quiz_number': bucket.get('quiz_number'),
                'deadline_date': bucket.get('deadline_date'),
                'available_from': bucket.get('available_from'),
            })
        results = self._enrich_component_scores_for_class(results, cls)
        results.sort(key=lambda item: self._component_sort_key(item))
        return results[:80]

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
            'deadline_late': 'deadline_late', 'late_deadline': 'deadline_late', 'quiz_deadline_late': 'deadline_late',
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
        expected_courses = {course for course in (course_by_class or {}).values() if course}
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
            progress_value = self._snapshot_progress_percent(snapshot)
            grade_value = self._snapshot_grade_percent(snapshot)
            if progress_value is not None:
                bucket['progress'].append(float(progress_value))
            if grade_value is not None:
                bucket['grades'].append(float(grade_value))
            if self._snapshot_has_learning_activity(snapshot):
                bucket['active'] = int(bucket.get('active', 0) or 0) + 1
            sync_at = snapshot.learning_synced_at or snapshot.last_synced_at
            if sync_at and (bucket['last_synced_at'] is None or sync_at > bucket['last_synced_at']):
                bucket['last_synced_at'] = sync_at
        result: dict[str, dict[str, Any]] = {}
        class_rows = self.db.query(AcademicClass).filter(AcademicClass.id.in_(class_ids)).all() if class_ids else []
        class_by_id_for_plan = {cls.id: cls for cls in class_rows}
        for class_id, bucket in buckets.items():
            total = int(totals.get(class_id, 0) or 0)
            counts = dict(bucket['counts'])
            synced = len(bucket['snapshots'])
            enrolled = int(counts.get('enrolled', 0) or 0)
            avg_progress = round(sum(bucket['progress']) / len(bucket['progress']), 2) if bucket['progress'] else None
            avg_grade = round(sum(bucket['grades']) / len(bucket['grades']), 2) if bucket['grades'] else None
            course_id = (course_by_class or {}).get(class_id)
            component_summaries = self._component_summary_from_snapshots(bucket['snapshots'], class_by_id_for_plan.get(class_id))
            result[class_id] = {
                'learning_enrolled_count': enrolled,
                'learning_active_count': int(bucket.get('active', 0) or 0),
                'learning_synced_count': synced,
                'learning_not_enrolled_count': max(0, total - enrolled),
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_last_synced_at': bucket['last_synced_at'],
                'learning_component_summaries': component_summaries,
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
            progress_value = self._snapshot_progress_percent(snapshot)
            grade_value = self._snapshot_grade_percent(snapshot)
            if progress_value is not None:
                bucket['progress'].append(float(progress_value))
            if grade_value is not None:
                bucket['grades'].append(float(grade_value))
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
        cache_key = f"exact:{raw.lower()}:{bool(allow_external)}"
        if cache_key in cache:
            return cache[cache_key]

        # Auto-map is an explicit user/admin action, so it must query CMS/Open edX
        # first. CourseSyncState is only a cache; a missing local cache entry must
        # not make the UI say the course does not exist when CMS has it.
        if allow_external:
            try:
                candidate, title, count, source = OpenEdXConnectorClient().find_exact_course(raw)
                if count == 1 and candidate:
                    result = (candidate, 1, title, source or 'cms_openedx_api_exact')
                    cache[cache_key] = result
                    return result
                if count > 1:
                    result = (None, count, None, source or 'cms_openedx_api_exact')
                    cache[cache_key] = result
                    return result
            except Exception:
                # Fallback to DB cache below. The caller will expose a useful
                # message if both API and cache fail.
                pass

        rows = self.db.query(CourseSyncState.course_id, CourseSyncState.display_name).filter(
            func.lower(CourseSyncState.course_id) == raw.lower(),
        ).distinct().limit(2).all()
        if len(rows) == 1:
            result = (str(rows[0][0]), 1, str(rows[0][1] or '') or None, 'course_cache_exact')
            cache[cache_key] = result
            return result

        result = (None, len(rows), None, 'course_cache_exact')
        cache[cache_key] = result
        return result

    def _find_openedx_course_candidate_for_scope(
        self,
        *,
        term: AcademicTerm,
        subject: AcademicSubject,
        suggested: str,
        allow_external: bool = True,
    ) -> dict[str, Any]:
        """Find one safe CMS/Open edX course candidate for a subject + term.

        The exact suggested course-v1 ID is tried first. If the deployment uses a
        different run naming convention, search CMS/Open edX by subject code and
        accept only when there is exactly one safe candidate. This avoids the old
        false negative where the course exists in CMS but was not present in the
        AI Server course cache.
        """
        exact_candidate, exact_count, exact_title, exact_source = self._find_exact_openedx_course_candidate(
            suggested,
            allow_external=allow_external,
        )
        if exact_candidate and exact_count == 1:
            return {
                'candidate': exact_candidate,
                'count': 1,
                'title': exact_title,
                'source': exact_source or 'cms_openedx_api_exact',
                'suggested_openedx_course_id': suggested,
                'candidates': [{'course_id': exact_candidate, 'display_name': exact_title, 'source': exact_source or 'cms_openedx_api_exact', 'match': 'exact'}],
            }

        subject_code = str(subject.subject_code or '').strip()
        if not subject_code:
            return {'candidate': None, 'count': 0, 'title': None, 'source': exact_source or 'empty_subject_code', 'suggested_openedx_course_id': suggested, 'candidates': []}

        term_candidates = _term_run_candidates(term)
        subject_key = _normalize_text_key(subject_code)
        seen: set[str] = set()
        raw_candidates: list[dict[str, Any]] = []

        if allow_external:
            try:
                api_rows = OpenEdXConnectorClient().search_courses(query=subject_code, exact_course_id=suggested, limit=50)
                for row in api_rows:
                    cid = str(row.get('course_id') or '').strip()
                    if cid and cid.lower() not in seen:
                        seen.add(cid.lower())
                        raw_candidates.append({'course_id': cid, 'display_name': row.get('display_name'), 'source': 'cms_openedx_api_search', 'raw': row})
            except Exception:
                pass

        # Cache fallback: useful when API is temporarily unavailable, but never
        # described to the user as the primary source for auto-map.
        cache_rows = self.db.query(CourseSyncState.course_id, CourseSyncState.display_name).filter(
            or_(
                func.lower(CourseSyncState.course_id).contains(subject_code.lower()),
                func.lower(CourseSyncState.display_name).contains(subject_code.lower()),
            )
        ).distinct().limit(100).all()
        for cid, title in cache_rows:
            value = str(cid or '').strip()
            if value and value.lower() not in seen:
                seen.add(value.lower())
                raw_candidates.append({'course_id': value, 'display_name': str(title or '') or None, 'source': 'course_cache_search'})

        def _subject_matches(course_id: str) -> bool:
            parsed = _parse_openedx_course_id(course_id)
            if parsed:
                return _normalize_text_key(parsed['course']) == subject_key
            return f'+{subject_key}+' in _normalize_text_key(course_id)

        def _term_score(item: dict[str, Any]) -> int:
            cid = str(item.get('course_id') or '')
            title = str(item.get('display_name') or '')
            parsed = _parse_openedx_course_id(cid)
            run_key = _clean_token(parsed['run']) if parsed else ''
            haystack = _clean_token(f'{cid} {title}')
            if term_candidates and run_key in term_candidates:
                return 3
            if term_candidates and any(candidate in haystack for candidate in term_candidates):
                return 2
            # When CMS has exactly one course for this subject, allow mapping even
            # if the run naming convention is not recognized. validate_* will keep
            # the term mismatch as a warning, not a hard failure.
            return 1

        subject_matches = [item for item in raw_candidates if _subject_matches(str(item.get('course_id') or ''))]
        if not subject_matches:
            return {'candidate': None, 'count': 0, 'title': None, 'source': exact_source or 'cms_openedx_api_search', 'suggested_openedx_course_id': suggested, 'candidates': raw_candidates[:10]}

        preferred = [item for item in subject_matches if _term_score(item) >= 2]
        candidates = preferred if preferred else subject_matches
        unique = {str(item['course_id']).lower(): item for item in candidates}
        candidates = list(unique.values())
        candidates.sort(key=lambda item: (-_term_score(item), str(item.get('course_id') or '')))

        if len(candidates) == 1:
            item = candidates[0]
            return {
                'candidate': str(item.get('course_id') or ''),
                'count': 1,
                'title': item.get('display_name'),
                'source': item.get('source') or 'cms_openedx_api_search',
                'suggested_openedx_course_id': suggested,
                'candidates': candidates[:10],
            }
        return {'candidate': None, 'count': len(candidates), 'title': None, 'source': 'cms_openedx_api_search', 'suggested_openedx_course_id': suggested, 'candidates': candidates[:10]}

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
        lookup = self._find_openedx_course_candidate_for_scope(term=term, subject=subject, suggested=suggested, allow_external=True)
        candidate = lookup.get('candidate')
        candidate_count = int(lookup.get('count') or 0)
        candidate_title = lookup.get('title')
        candidate_source = str(lookup.get('source') or 'cms_openedx_api')
        if candidate_count != 1 or not candidate:
            status_value = 'not_found' if candidate_count == 0 else 'multiple_candidates'
            return {
                'ok': False,
                'status': status_value,
                'message': 'Chưa tìm thấy đúng một Course CMS khớp mã môn/kỳ qua API CMS/Open edX. Hãy kiểm tra OPENEDX_CONNECTOR_BASE_URL, OPENEDX_CONNECTOR_HMAC_SECRET và endpoint /api/ai-connector/v1/courses/search; nếu có nhiều course cùng mã môn, cần map thủ công để tránh nhầm kỳ.',
                'suggested_openedx_course_id': suggested,
                'candidate_count': candidate_count,
                'candidate_source': candidate_source,
                'candidates': lookup.get('candidates') or [],
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
            'quiz_count': 0,
        }

    def _student_mapping_item(
        self,
        class_id: str,
        student: AcademicStudent,
        synced_at: datetime | None,
        mapping: OpenEdXUserMapping | None,
        learning: AcademicStudentLearningSnapshot | None = None,
        class_student: AcademicClassStudent | None = None,
        *,
        cls: AcademicClass | None = None,
        block: AcademicBlock | None = None,
        policy_service: TrainingPolicyService | None = None,
        assignment_scores: dict[str, Any] | None = None,
        deadline_overrides: dict[int, Any] | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        cls = cls or self.db.get(AcademicClass, class_id)
        block = block if block is not None else (self._block_for_class(cls) if cls else None)
        components = self._enrich_component_scores_for_class(self._component_scores_from_snapshot(learning), cls)
        course_id = course_id or (learning.openedx_course_id if learning else None)
        policy_service = policy_service or TrainingPolicyService(self.db)
        if assignment_scores is None:
            assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id)
        if deadline_overrides is None:
            deadline_overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
        training_policy = policy_service.evaluate_student(
            cls=cls,
            student_id=student.id,
            components=components,
            block=block,
            course_id=course_id,
            assignment_score=assignment_scores.get(student.id),
            overrides=deadline_overrides,
        )
        return {
            'class_id': class_id,
            'id': student.id,
            'student_code': student.student_code,
            'username': student.username,
            'email': student.email,
            'full_name': student.full_name,
            'phone': student.phone,
            'total_relearn': self._metadata_total_relearn(class_student.metadata_json if class_student else None, student.metadata_json),
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
            'learning_progress_percent': self._snapshot_progress_percent(learning),
            'learning_grade_percent': self._snapshot_grade_percent(learning),
            'learning_passed': learning.passed if learning else None,
            'learning_completed_blocks': learning.completed_blocks if learning else None,
            'learning_total_blocks': learning.total_blocks if learning else None,
            'learning_last_activity_at': learning.last_activity_at if learning else None,
            'learning_last_synced_at': (learning.learning_synced_at or learning.last_synced_at) if learning else None,
            'learning_enrollment_synced_at': learning.enrollment_synced_at if learning else None,
            'learning_status': self._learning_status_for_snapshot(learning, mapping),
            'learning_component_scores': components,
            'training_policy': training_policy,
            'exam_eligible': training_policy.get('exam_eligible'),
            'exam_status': training_policy.get('exam_status'),
            'exam_status_label': training_policy.get('exam_status_label'),
            'exam_reasons': training_policy.get('exam_reasons') or [],
            'assignment_defense_status': training_policy.get('assignment_status'),
            'assignment_score_10': training_policy.get('assignment_score_10'),
        }

    def list_class_students(self, user: UserContext, class_id: str, *, search: str | None = None, learning_status: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        page, page_size = _page(page, page_size)
        cls = self.db.get(AcademicClass, class_id)
        effective_mapping = self.effective_course_mapping_for_class(cls) if cls else None
        course_id = effective_mapping.openedx_course_id if effective_mapping else None
        query = self.db.query(AcademicStudent, AcademicClassStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
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
        block = self._block_for_class(cls) if cls else None
        policy_service = TrainingPolicyService(self.db)
        assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id)
        deadline_overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
        items = [
            self._student_mapping_item(
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
            )
            for student, class_student, mapping, learning in rows
        ]
        total_pages = math.ceil(total / page_size) if total else 0
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages}

    @staticmethod
    def _percent_to_grade10(value: Any) -> float | None:
        if value is None or value == '':
            return None
        try:
            number = float(value)
        except Exception:
            return None
        if 0 <= number <= 1:
            number *= 100.0
        return round(max(0.0, min(100.0, number)) / 10.0, 2)

    def _learning_status_label(self, status_name: str | None) -> str:
        labels = {
            'cms_not_synced': 'Chưa đồng bộ CMS',
            'not_synced': 'Chưa cập nhật học tập',
            'not_enrolled': 'Chưa enroll',
            'sync_error': 'Lỗi đồng bộ',
            'no_activity': 'Chưa học',
            'low_progress': 'Tiến độ thấp',
            'low_grade': 'Điểm thấp',
            'in_progress': 'Đang học',
            'good': 'Ổn',
        }
        return labels.get(str(status_name or ''), str(status_name or 'Không rõ'))

    def _training_learning_status_counts_by_class(
        self,
        class_ids: list[str],
        course_by_class: dict[str, str | None],
    ) -> tuple[dict[str, dict[str, int]], dict[tuple[str, str], AcademicStudentLearningSnapshot]]:
        if not class_ids:
            return {}, {}
        snapshots = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id.in_(class_ids)
        ).all()
        snapshot_by_class_student: dict[tuple[str, str], AcademicStudentLearningSnapshot] = {}
        for snapshot in snapshots:
            expected_course = course_by_class.get(snapshot.class_id)
            if expected_course and snapshot.openedx_course_id != expected_course:
                continue
            if not expected_course:
                continue
            snapshot_by_class_student[(snapshot.class_id, snapshot.student_id)] = snapshot

        rows = self.db.query(
            AcademicClassStudent.class_id,
            AcademicClassStudent.student_id,
            OpenEdXUserMapping,
        ).outerjoin(
            OpenEdXUserMapping,
            OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
        ).filter(AcademicClassStudent.class_id.in_(class_ids)).all()

        counts_by_class: dict[str, dict[str, int]] = {class_id: {} for class_id in class_ids}
        for class_id, student_id, mapping in rows:
            status_name = self._learning_status_for_snapshot(snapshot_by_class_student.get((class_id, student_id)), mapping)
            bucket = counts_by_class.setdefault(class_id, {})
            bucket[status_name] = bucket.get(status_name, 0) + 1
        return counts_by_class, snapshot_by_class_student

    def training_teacher_report(
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
        include_all: bool = False,
        include_students: bool = False,
    ) -> dict[str, Any]:
        page, page_size = _page(page, page_size)
        decision = self.access_decision(user)
        status_filter = self._normalize_learning_list_filter(learning_status)
        query = self.db.query(
            AcademicTeacher,
            AcademicTeacherAssignment,
            AcademicClass,
            AcademicTerm,
            AcademicBlock,
            AcademicSubject,
        ).join(
            AcademicTeacherAssignment,
            AcademicTeacherAssignment.teacher_id == AcademicTeacher.id,
        ).join(
            AcademicClass,
            AcademicClass.id == AcademicTeacherAssignment.class_id,
        ).join(
            AcademicTerm,
            AcademicTerm.id == AcademicClass.term_id,
        ).outerjoin(
            AcademicBlock,
            AcademicBlock.id == AcademicClass.block_id,
        ).join(
            AcademicSubject,
            AcademicSubject.id == AcademicClass.subject_id,
        ).filter(
            AcademicTeacher.active.is_(True),
            AcademicClass.active.is_(True),
            AcademicSubject.active.is_(True),
        )
        query = self._apply_academic_access_filter(query, user, decision)
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(AcademicClass.campus == campus.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicTeacher.username.ilike(like),
                AcademicTeacher.full_name.ilike(like),
                AcademicTeacher.email.ilike(like),
                AcademicClass.class_code.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
            ))
        rows = query.order_by(
            AcademicTeacher.full_name.asc().nullslast(),
            AcademicTeacher.username.asc(),
            AcademicTerm.start_date.desc().nullslast(),
            AcademicSubject.subject_code.asc(),
            AcademicClass.class_code.asc(),
        ).all()

        class_by_id: dict[str, AcademicClass] = {}
        block_by_class: dict[str, AcademicBlock | None] = {}
        class_context: dict[str, dict[str, Any]] = {}
        for teacher, assignment, cls, term, block, subject in rows:
            class_by_id[cls.id] = cls
            block_by_class[cls.id] = block
            class_context[cls.id] = {
                'term_name': term.term_name if term else None,
                'block_name': block.block_name if block else None,
                'subject_code': subject.subject_code if subject else None,
                'subject_name': subject.subject_name if subject else None,
            }
        class_ids = list(class_by_id.keys())

        student_rows = self.db.query(AcademicClassStudent.class_id, AcademicClassStudent.student_id, AcademicClassStudent.metadata_json).filter(
            AcademicClassStudent.class_id.in_(class_ids)
        ).all() if class_ids else []
        student_ids_by_class: dict[str, set[str]] = {class_id: set() for class_id in class_ids}
        relearn_by_class: dict[str, dict[str, int]] = {class_id: {'student_count': 0, 'total': 0} for class_id in class_ids}
        relearn_by_class_student: dict[tuple[str, str], int] = {}
        for class_id, student_id, meta in student_rows:
            student_ids_by_class.setdefault(class_id, set()).add(student_id)
            total_relearn = self._metadata_total_relearn(meta)
            relearn_by_class_student[(class_id, student_id)] = total_relearn
            if total_relearn > 0:
                bucket = relearn_by_class.setdefault(class_id, {'student_count': 0, 'total': 0})
                bucket['student_count'] += 1
                bucket['total'] += total_relearn
        student_count_by_class = {class_id: len(ids) for class_id, ids in student_ids_by_class.items()}

        sync_by_class = self._student_sync_summary_for_classes(class_ids)
        class_overrides = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id.in_(class_ids),
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).all() if class_ids else []
        override_by_class = {item.class_id: item for item in class_overrides}
        inherited_by_class = self.inherited_course_mappings_for_classes(list(class_by_id.values()))
        course_by_class: dict[str, str | None] = {}
        mapping_source_by_class: dict[str, str | None] = {}
        for class_id, cls in class_by_id.items():
            mapping = override_by_class.get(class_id) or inherited_by_class.get(class_id)
            course_by_class[class_id] = mapping.openedx_course_id if mapping else None
            mapping_source_by_class[class_id] = 'class_override' if class_id in override_by_class else ('subject_term_mapping' if mapping else None)

        learning_by_class = self._learning_summary_by_class_ids(class_ids, course_by_class)
        status_counts_by_class, snapshot_by_class_student = self._training_learning_status_counts_by_class(class_ids, course_by_class)
        deadline_by_class, deadline_by_class_student = self._training_deadline_status_by_class(class_by_id, block_by_class, snapshot_by_class_student)

        policy_service = TrainingPolicyService(self.db)
        policy_by_class_student: dict[tuple[str, str], dict[str, Any]] = {}
        policy_summary_by_class: dict[str, dict[str, int]] = {}
        for class_id, cls in class_by_id.items():
            course_id = course_by_class.get(class_id)
            overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
            assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id)
            summary_bucket = {
                'exam_eligible_student_count': 0,
                'exam_not_eligible_student_count': 0,
                'exam_insufficient_data_student_count': 0,
                'quiz_failed_count': 0,
                'quiz_late_count': 0,
                'quiz_not_attempted_count': 0,
                'quiz_missing_deadline_count': 0,
                'assignment_not_graded_count': 0,
            }
            for student_id in student_ids_by_class.get(class_id, set()):
                snapshot = snapshot_by_class_student.get((class_id, student_id))
                components = self._enrich_component_scores_for_class(self._component_scores_from_snapshot(snapshot), cls)
                policy = policy_service.evaluate_student(
                    cls=cls,
                    student_id=student_id,
                    components=components,
                    block=block_by_class.get(class_id),
                    course_id=course_id,
                    assignment_score=assignment_scores.get(student_id),
                    overrides=overrides,
                )
                policy_by_class_student[(class_id, student_id)] = policy
                status_name = str(policy.get('exam_status') or '')
                if status_name == 'eligible':
                    summary_bucket['exam_eligible_student_count'] += 1
                elif status_name == 'not_eligible':
                    summary_bucket['exam_not_eligible_student_count'] += 1
                else:
                    summary_bucket['exam_insufficient_data_student_count'] += 1
                summary_bucket['quiz_failed_count'] += int(policy.get('quiz_failed_count') or 0)
                summary_bucket['quiz_late_count'] += int(policy.get('quiz_late_count') or 0)
                summary_bucket['quiz_not_attempted_count'] += int(policy.get('quiz_not_attempted_count') or 0)
                summary_bucket['quiz_missing_deadline_count'] += int(policy.get('quiz_missing_deadline_count') or 0)
                if policy.get('assignment_expected') and policy.get('assignment_status') != 'graded':
                    summary_bucket['assignment_not_graded_count'] += 1
            policy_summary_by_class[class_id] = summary_bucket

        teacher_buckets: dict[str, dict[str, Any]] = {}
        seen_teacher_classes: set[tuple[str, str]] = set()
        class_teacher_context: dict[str, list[dict[str, Any]]] = {}
        for teacher, assignment, cls, term, block, subject in rows:
            key = teacher.id
            bucket = teacher_buckets.setdefault(key, {
                'teacher_id': teacher.id,
                'teacher_code': teacher.teacher_code,
                'teacher_username': teacher.username,
                'teacher_name': teacher.full_name or teacher.username,
                'teacher_email': teacher.email,
                'campus': teacher.campus or cls.campus,
                'branch': teacher.branch or cls.branch,
                'subject_ids': set(),
                'subject_codes': set(),
                'class_ids': set(),
                'unique_student_ids': set(),
                'student_count': 0,
                'cms_synced_count': 0,
                'cms_unsynced_count': 0,
                'learning_enrolled_count': 0,
                'learning_active_count': 0,
                'learning_synced_count': 0,
                'classes_without_course_count': 0,
                'deadline_late_student_count': 0,
                'deadline_late_quiz_count': 0,
                'deadline_due_quiz_count': 0,
                'exam_eligible_student_count': 0,
                'exam_not_eligible_student_count': 0,
                'exam_insufficient_data_student_count': 0,
                'quiz_failed_count': 0,
                'quiz_late_count': 0,
                'quiz_not_attempted_count': 0,
                'quiz_missing_deadline_count': 0,
                'assignment_not_graded_count': 0,
                'relearn_student_count': 0,
                'total_relearn_count': 0,
                'progress_weighted_sum': 0.0,
                'progress_weight': 0,
                'grade_weighted_sum': 0.0,
                'grade_weight': 0,
                'status_counts': {},
                'class_items': [],
                'last_synced_at': None,
            })
            class_teacher_context.setdefault(cls.id, []).append({
                'teacher_id': teacher.id,
                'teacher_username': teacher.username,
                'teacher_name': teacher.full_name or teacher.username,
                'teacher_email': teacher.email,
            })
            pair = (teacher.id, cls.id)
            if pair in seen_teacher_classes:
                continue
            seen_teacher_classes.add(pair)
            bucket['class_ids'].add(cls.id)
            bucket['subject_ids'].add(subject.id)
            bucket['subject_codes'].add(subject.subject_code)
            class_student_ids = student_ids_by_class.get(cls.id, set())
            bucket['unique_student_ids'].update(class_student_ids)
            class_student_count = int(student_count_by_class.get(cls.id, 0) or 0)
            class_relearn = relearn_by_class.get(cls.id, {})
            relearn_student_count = int(class_relearn.get('student_count') or 0)
            total_relearn_count = int(class_relearn.get('total') or 0)
            bucket['student_count'] += class_student_count
            bucket['relearn_student_count'] += relearn_student_count
            bucket['total_relearn_count'] += total_relearn_count
            sync_counts = sync_by_class.get(cls.id, {})
            cms_synced = int(sync_counts.get('matched', 0) or 0)
            cms_unsynced = max(0, class_student_count - cms_synced)
            bucket['cms_synced_count'] += cms_synced
            bucket['cms_unsynced_count'] += cms_unsynced
            learning = learning_by_class.get(cls.id, {})
            enrolled = int(learning.get('learning_enrolled_count') or 0)
            active = int(learning.get('learning_active_count') or 0)
            synced = int(learning.get('learning_synced_count') or 0)
            bucket['learning_enrolled_count'] += enrolled
            bucket['learning_active_count'] += active
            bucket['learning_synced_count'] += synced
            if not course_by_class.get(cls.id):
                bucket['classes_without_course_count'] += 1
            avg_progress = learning.get('learning_avg_progress_percent')
            avg_grade = learning.get('learning_avg_grade_percent')
            if isinstance(avg_progress, (int, float)) and synced:
                bucket['progress_weighted_sum'] += float(avg_progress) * synced
                bucket['progress_weight'] += synced
            if isinstance(avg_grade, (int, float)) and synced:
                bucket['grade_weighted_sum'] += float(avg_grade) * synced
                bucket['grade_weight'] += synced
            status_counts = status_counts_by_class.get(cls.id, {})
            for status_name, count in status_counts.items():
                bucket['status_counts'][status_name] = int(bucket['status_counts'].get(status_name, 0) or 0) + int(count or 0)
            last_synced = learning.get('learning_last_synced_at')
            if last_synced and (bucket['last_synced_at'] is None or last_synced > bucket['last_synced_at']):
                bucket['last_synced_at'] = last_synced
            deadline = deadline_by_class.get(cls.id, {})
            deadline_late_students = int(deadline.get('late_student_count') or 0)
            deadline_late_quizzes = int(deadline.get('late_quiz_count') or 0)
            deadline_due_quizzes = int(deadline.get('due_quiz_count') or 0)
            bucket['deadline_late_student_count'] += deadline_late_students
            bucket['deadline_late_quiz_count'] += deadline_late_quizzes
            bucket['deadline_due_quiz_count'] += deadline_due_quizzes
            policy_summary = policy_summary_by_class.get(cls.id, {})
            for policy_key in ('exam_eligible_student_count', 'exam_not_eligible_student_count', 'exam_insufficient_data_student_count', 'quiz_failed_count', 'quiz_late_count', 'quiz_not_attempted_count', 'quiz_missing_deadline_count', 'assignment_not_graded_count'):
                bucket[policy_key] += int(policy_summary.get(policy_key) or 0)
            if int(policy_summary.get('exam_not_eligible_student_count') or 0):
                bucket['status_counts']['exam_not_eligible'] = int(bucket['status_counts'].get('exam_not_eligible', 0) or 0) + int(policy_summary.get('exam_not_eligible_student_count') or 0)
            if int(policy_summary.get('exam_insufficient_data_student_count') or 0):
                bucket['status_counts']['exam_insufficient_data'] = int(bucket['status_counts'].get('exam_insufficient_data', 0) or 0) + int(policy_summary.get('exam_insufficient_data_student_count') or 0)
            if deadline_late_students:
                bucket['status_counts']['deadline_late'] = int(bucket['status_counts'].get('deadline_late', 0) or 0) + deadline_late_students
            alerts = list(learning.get('learning_alerts') or [])
            if not course_by_class.get(cls.id) and 'Chưa map Course CMS' not in alerts:
                alerts.append('Chưa map Course CMS')
            if deadline_late_students:
                alerts.append(f'{deadline_late_students} SV trễ deadline quiz ({deadline_late_quizzes} lượt quiz)')
            bucket['class_items'].append({
                'class_id': cls.id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'term_id': cls.term_id,
                'term_name': term.term_name if term else None,
                'block_id': cls.block_id,
                'block_name': block.block_name if block else None,
                'subject_id': subject.id,
                'subject_code': subject.subject_code,
                'subject_name': subject.subject_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'student_count': class_student_count,
                'relearn_student_count': relearn_student_count,
                'total_relearn_count': total_relearn_count,
                'cms_synced_count': cms_synced,
                'cms_unsynced_count': cms_unsynced,
                'openedx_course_id': course_by_class.get(cls.id),
                'openedx_mapping_source': mapping_source_by_class.get(cls.id),
                'learning_enrolled_count': enrolled,
                'learning_active_count': active,
                'learning_synced_count': synced,
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_avg_grade_10': self._percent_to_grade10(avg_grade),
                'learning_last_synced_at': last_synced,
                'learning_component_summaries': learning.get('learning_component_summaries') or [],
                'status_counts': status_counts,
                'learning_alerts': alerts,
                'deadline_quiz_count': int(deadline.get('quiz_count') or 0),
                'deadline_due_quiz_count': deadline_due_quizzes,
                'deadline_completed_due_quiz_count': int(deadline.get('completed_due_quiz_count') or 0),
                'deadline_late_student_count': deadline_late_students,
                'deadline_late_quiz_count': deadline_late_quizzes,
                'deadline_next_quiz_label': deadline.get('next_quiz_label'),
                'deadline_next_quiz_from_date': deadline.get('next_quiz_from_date'),
                'deadline_next_quiz_due_date': deadline.get('next_quiz_due_date'),
                'deadline_schedule_note': deadline.get('schedule_note'),
                'exam_eligible_student_count': int(policy_summary.get('exam_eligible_student_count') or 0),
                'exam_not_eligible_student_count': int(policy_summary.get('exam_not_eligible_student_count') or 0),
                'exam_insufficient_data_student_count': int(policy_summary.get('exam_insufficient_data_student_count') or 0),
                'quiz_failed_count': int(policy_summary.get('quiz_failed_count') or 0),
                'quiz_late_count': int(policy_summary.get('quiz_late_count') or 0),
                'quiz_not_attempted_count': int(policy_summary.get('quiz_not_attempted_count') or 0),
                'quiz_missing_deadline_count': int(policy_summary.get('quiz_missing_deadline_count') or 0),
                'assignment_not_graded_count': int(policy_summary.get('assignment_not_graded_count') or 0),
            })

        items: list[dict[str, Any]] = []
        alert_keys = ['cms_not_synced', 'not_synced', 'not_enrolled', 'sync_error', 'no_activity', 'low_progress', 'low_grade', 'deadline_late', 'exam_not_eligible', 'exam_insufficient_data']
        for bucket in teacher_buckets.values():
            status_counts = dict(bucket['status_counts'])
            avg_progress = round(bucket['progress_weighted_sum'] / bucket['progress_weight'], 2) if bucket['progress_weight'] else None
            avg_grade = round(bucket['grade_weighted_sum'] / bucket['grade_weight'], 2) if bucket['grade_weight'] else None
            risk_student_count = int(sum(int(status_counts.get(key, 0) or 0) for key in alert_keys))
            learning_alerts: list[str] = []
            if bucket['classes_without_course_count']:
                learning_alerts.append(f"{bucket['classes_without_course_count']} lớp chưa map Course CMS")
            if int(status_counts.get('cms_not_synced', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('cms_not_synced', 0) or 0)} SV chưa đồng bộ CMS")
            if int(status_counts.get('not_enrolled', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('not_enrolled', 0) or 0)} SV chưa enroll")
            if int(status_counts.get('no_activity', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('no_activity', 0) or 0)} SV chưa học")
            if int(status_counts.get('low_progress', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_progress', 0) or 0)} SV tiến độ thấp")
            if int(status_counts.get('low_grade', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_grade', 0) or 0)} SV điểm thấp")
            if int(status_counts.get('deadline_late', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('deadline_late', 0) or 0)} SV trễ deadline quiz")
            if int(status_counts.get('exam_not_eligible', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('exam_not_eligible', 0) or 0)} SV không được thi")
            if int(status_counts.get('exam_insufficient_data', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('exam_insufficient_data', 0) or 0)} SV chưa đủ dữ liệu xét thi")
            item = {
                'teacher_id': bucket['teacher_id'],
                'teacher_code': bucket['teacher_code'],
                'teacher_username': bucket['teacher_username'],
                'teacher_name': bucket['teacher_name'],
                'teacher_email': bucket['teacher_email'],
                'campus': bucket['campus'],
                'branch': bucket['branch'],
                'subject_count': len(bucket['subject_ids']),
                'subject_codes': sorted(bucket['subject_codes']),
                'class_count': len(bucket['class_ids']),
                'student_count': int(bucket['student_count']),
                'unique_student_count': len(bucket['unique_student_ids']),
                'relearn_student_count': int(bucket['relearn_student_count']),
                'total_relearn_count': int(bucket['total_relearn_count']),
                'cms_synced_count': int(bucket['cms_synced_count']),
                'cms_unsynced_count': int(bucket['cms_unsynced_count']),
                'learning_enrolled_count': int(bucket['learning_enrolled_count']),
                'learning_active_count': int(bucket['learning_active_count']),
                'learning_synced_count': int(bucket['learning_synced_count']),
                'classes_without_course_count': int(bucket['classes_without_course_count']),
                'deadline_late_student_count': int(bucket['deadline_late_student_count']),
                'deadline_late_quiz_count': int(bucket['deadline_late_quiz_count']),
                'deadline_due_quiz_count': int(bucket['deadline_due_quiz_count']),
                'exam_eligible_student_count': int(bucket['exam_eligible_student_count']),
                'exam_not_eligible_student_count': int(bucket['exam_not_eligible_student_count']),
                'exam_insufficient_data_student_count': int(bucket['exam_insufficient_data_student_count']),
                'quiz_failed_count': int(bucket['quiz_failed_count']),
                'quiz_late_count': int(bucket['quiz_late_count']),
                'quiz_not_attempted_count': int(bucket['quiz_not_attempted_count']),
                'quiz_missing_deadline_count': int(bucket['quiz_missing_deadline_count']),
                'assignment_not_graded_count': int(bucket['assignment_not_graded_count']),
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_avg_grade_10': self._percent_to_grade10(avg_grade),
                'risk_student_count': risk_student_count,
                'status_counts': status_counts,
                'learning_alerts': learning_alerts,
                'last_synced_at': bucket['last_synced_at'],
                'classes': sorted(bucket['class_items'], key=lambda item: (str(item.get('subject_code') or ''), str(item.get('class_code') or ''))),
            }
            items.append(item)

        def matches_training_filter(item: dict[str, Any]) -> bool:
            if status_filter == 'all':
                return True
            status_counts = item.get('status_counts') or {}
            if status_filter == 'no_course_map':
                return int(item.get('classes_without_course_count') or 0) > 0
            if status_filter == 'cms_not_synced':
                return int(status_counts.get('cms_not_synced', 0) or 0) > 0 or int(item.get('cms_unsynced_count') or 0) > 0
            if status_filter == 'not_fully_enrolled':
                return int(status_counts.get('not_enrolled', 0) or 0) > 0 or int(item.get('learning_enrolled_count') or 0) < int(item.get('student_count') or 0)
            if status_filter == 'no_learning_data':
                return int(item.get('learning_synced_count') or 0) == 0 and int(item.get('student_count') or 0) > 0
            if status_filter in {'no_activity', 'low_progress', 'low_grade', 'sync_error', 'deadline_late', 'exam_not_eligible', 'exam_insufficient_data'}:
                return int(status_counts.get(status_filter, 0) or 0) > 0
            if status_filter == 'has_alert':
                return bool(item.get('learning_alerts')) or int(item.get('risk_student_count') or 0) > 0
            return True

        filtered_items = [item for item in items if matches_training_filter(item)]
        filtered_items.sort(key=lambda item: (str(item.get('teacher_name') or ''), str(item.get('teacher_username') or '')))
        total = len(filtered_items)
        if include_all:
            page_items = filtered_items
            total_pages = 1 if total else 0
        else:
            page_items = filtered_items[(page - 1) * page_size: page * page_size]
            total_pages = math.ceil(total / page_size) if total else 0
        summary = {
            'teacher_count': total,
            'class_count': sum(int(item.get('class_count') or 0) for item in filtered_items),
            'subject_count': len({code for item in filtered_items for code in (item.get('subject_codes') or [])}),
            'student_count': sum(int(item.get('student_count') or 0) for item in filtered_items),
            'unique_student_count': sum(int(item.get('unique_student_count') or 0) for item in filtered_items),
            'relearn_student_count': sum(int(item.get('relearn_student_count') or 0) for item in filtered_items),
            'total_relearn_count': sum(int(item.get('total_relearn_count') or 0) for item in filtered_items),
            'cms_synced_count': sum(int(item.get('cms_synced_count') or 0) for item in filtered_items),
            'learning_enrolled_count': sum(int(item.get('learning_enrolled_count') or 0) for item in filtered_items),
            'learning_active_count': sum(int(item.get('learning_active_count') or 0) for item in filtered_items),
            'risk_student_count': sum(int(item.get('risk_student_count') or 0) for item in filtered_items),
            'classes_without_course_count': sum(int(item.get('classes_without_course_count') or 0) for item in filtered_items),
            'deadline_late_student_count': sum(int(item.get('deadline_late_student_count') or 0) for item in filtered_items),
            'deadline_late_quiz_count': sum(int(item.get('deadline_late_quiz_count') or 0) for item in filtered_items),
            'exam_eligible_student_count': sum(int(item.get('exam_eligible_student_count') or 0) for item in filtered_items),
            'exam_not_eligible_student_count': sum(int(item.get('exam_not_eligible_student_count') or 0) for item in filtered_items),
            'exam_insufficient_data_student_count': sum(int(item.get('exam_insufficient_data_student_count') or 0) for item in filtered_items),
            'quiz_failed_count': sum(int(item.get('quiz_failed_count') or 0) for item in filtered_items),
            'assignment_not_graded_count': sum(int(item.get('assignment_not_graded_count') or 0) for item in filtered_items),
        }
        result: dict[str, Any] = {'items': page_items, 'summary': summary, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': (not include_all and page < total_pages)}

        if include_students and class_ids:
            student_query = self.db.query(
                AcademicClassStudent.class_id,
                AcademicClassStudent.metadata_json,
                AcademicStudent,
                OpenEdXUserMapping,
            ).join(
                AcademicStudent,
                AcademicStudent.id == AcademicClassStudent.student_id,
            ).outerjoin(
                OpenEdXUserMapping,
                OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
            ).filter(AcademicClassStudent.class_id.in_(class_ids))
            watch_rows: list[dict[str, Any]] = []
            for class_id, class_student_meta, student, mapping in student_query.order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).all():
                snapshot = snapshot_by_class_student.get((class_id, student.id))
                status_name = self._learning_status_for_snapshot(snapshot, mapping)
                deadline_status = deadline_by_class_student.get((class_id, student.id), {})
                policy = policy_by_class_student.get((class_id, student.id), {})
                if status_name in {'good', 'in_progress'} and int(deadline_status.get('late_quiz_count') or 0) <= 0 and policy.get('exam_status') != 'not_eligible':
                    continue
                for teacher_ctx in class_teacher_context.get(class_id, []):
                    context = class_context.get(class_id, {})
                    watch_rows.append({
                        **teacher_ctx,
                        'class_id': class_id,
                        'class_code': class_by_id[class_id].class_code if class_id in class_by_id else '',
                        'term_name': context.get('term_name'),
                        'block_name': context.get('block_name'),
                        'subject_code': context.get('subject_code'),
                        'subject_name': context.get('subject_name'),
                        'student_code': student.student_code,
                        'student_username': student.username,
                        'student_name': student.full_name,
                        'student_email': student.email,
                        'total_relearn': self._metadata_total_relearn(class_student_meta, student.metadata_json),
                        'openedx_username': mapping.openedx_username if mapping else None,
                        'status': status_name,
                        'status_label': self._learning_status_label(status_name),
                        'enrollment_status': snapshot.enrollment_status if snapshot else None,
                        'progress_percent': self._snapshot_progress_percent(snapshot),
                        'grade_percent': self._snapshot_grade_percent(snapshot),
                        'grade_10': self._percent_to_grade10(self._snapshot_grade_percent(snapshot)),
                        'last_activity_at': snapshot.last_activity_at if snapshot else None,
                        'last_synced_at': (snapshot.learning_synced_at or snapshot.last_synced_at) if snapshot else None,
                        'exam_status': policy.get('exam_status'),
                        'exam_status_label': policy.get('exam_status_label'),
                        'exam_reasons': policy.get('exam_reasons') or [],
                        'quiz_passed_count': policy.get('quiz_passed_count'),
                        'quiz_failed_count': policy.get('quiz_failed_count'),
                        'quiz_not_attempted_count': policy.get('quiz_not_attempted_count'),
                        'assignment_status': policy.get('assignment_status'),
                        'assignment_score_10': policy.get('assignment_score_10'),
                        'deadline_due_quiz_count': int(deadline_status.get('due_quiz_count') or 0),
                        'deadline_completed_due_quiz_count': int(deadline_status.get('completed_due_quiz_count') or 0),
                        'deadline_late_quiz_count': int(deadline_status.get('late_quiz_count') or 0),
                        'deadline_late_quizzes': deadline_status.get('late_quizzes') or [],
                        'deadline_next_quiz_label': deadline_status.get('next_quiz_label'),
                        'deadline_next_quiz_from_date': deadline_status.get('next_quiz_from_date'),
                        'deadline_next_quiz_due_date': deadline_status.get('next_quiz_due_date'),
                    })
                    if len(watch_rows) >= 20000:
                        break
                if len(watch_rows) >= 20000:
                    break
            result['student_watch_rows'] = watch_rows
        return result

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
        checks.append(_check('openedx_live_validation', 'warn', 'Chưa validate live course structure. Bản sau sẽ dùng LMS Open edX Connector để kiểm tra course/cohort thật.', blocking=False))
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

    def _snapshot_has_learning_payload(self, snapshot: AcademicStudentLearningSnapshot | None) -> bool:
        if not snapshot:
            return False
        if self._snapshot_progress_percent(snapshot) is not None or self._snapshot_grade_percent(snapshot) is not None:
            return True
        if snapshot.completed_blocks is not None or snapshot.total_blocks is not None:
            return True
        return bool(self._component_scores_from_snapshot(snapshot))

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
            **_json_safe_value(existing),
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

    def resolve_class_openedx_users(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, auto_enroll: bool = True) -> dict[str, Any]:
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

        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
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
                mapping = self._upsert_mapping(student, result, source='openedx_connector')
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
        if auto_enroll and getattr(settings, 'academic_auto_enroll_after_cms_sync', True):
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
        last_synced = self.db.query(func.max(func.coalesce(AcademicStudentLearningSnapshot.learning_synced_at, AcademicStudentLearningSnapshot.last_synced_at))).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).scalar()
        snapshots = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).all()
        progress_values = [value for value in (self._snapshot_progress_percent(snapshot) for snapshot in snapshots) if value is not None]
        grade_values = [value for value in (self._snapshot_grade_percent(snapshot) for snapshot in snapshots) if value is not None]
        avg_progress = round(sum(progress_values) / len(progress_values), 2) if progress_values else None
        avg_grade = round(sum(grade_values) / len(grade_values), 2) if grade_values else None
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
            'avg_progress_percent': avg_progress,
            'avg_grade_percent': avg_grade,
            'last_synced_at': last_synced,
            'component_summaries': (self._component_summary_from_snapshots(snapshots, self.db.get(AcademicClass, class_id))),
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
        if snapshot.progress_percent is None:
            snapshot.progress_percent = self._progress_percent_from_payload(result)
        snapshot.grade_percent = self._float_or_none(result.get('grade_percent', grade.get('percent')))
        if snapshot.grade_percent is None:
            snapshot.grade_percent = self._grade_percent_from_payload(result)
        if 'passed' in result:
            snapshot.passed = _boolish(result.get('passed'))
        elif 'passed' in grade:
            snapshot.passed = _boolish(grade.get('passed'))
        snapshot.completed_blocks = self._int_or_none(result.get('completed_blocks', progress.get('completed_blocks')))
        snapshot.total_blocks = self._int_or_none(result.get('total_blocks', progress.get('total_blocks')))
        snapshot.last_activity_at = self._dt_or_none(result.get('last_activity_at') or progress.get('last_activity_at'))
        snapshot.raw_json = {'source': source, 'payload': _json_safe_value(result)}
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
        snapshot.raw_json = {**_json_safe_value(existing_raw), 'enrollment_source': source, 'enrollment_payload': _json_safe_value(result)}
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

        # Full production behavior: enrollment must not silently skip learners just
        # because they have not been mapped yet. First resolve/create CMS users by
        # AP username, then enroll matched/created users. The nested call disables
        # auto-enroll to avoid recursion.
        if getattr(settings, 'academic_auto_create_cms_users', True):
            try:
                self.resolve_class_openedx_users(user, class_id, force=force, limit=limit, auto_enroll=False)
            except HTTPException:
                raise
            except Exception as exc:
                raise RuntimeError(f'Không tạo/kiểm tra được tài khoản CMS trước khi enrollment: {exc}') from exc

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
        matched_student_count = len(rows)
        if not force:
            rows = [(student, mapping_row, snapshot) for student, mapping_row, snapshot in rows if not snapshot or snapshot.enrollment_status not in {'enrolled'}]

        class_student_count = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == class_id).scalar() or 0
        if int(class_student_count) > 0 and matched_student_count == 0:
            raise HTTPException(
                status_code=400,
                detail='Chưa có sinh viên nào được map user CMS/Open edX chính xác. Hãy chạy Tạo/kiểm tra user CMS trước rồi mới Enrollment Course CMS.',
            )

        teacher_payload = self._teacher_payload_for_class(class_id) if getattr(settings, 'academic_auto_add_teachers_to_course', True) else []
        if not rows and not teacher_payload:
            summary = self._learning_summary_for_class_course(class_id, course_id)
            return {'ok': True, 'class_id': class_id, 'openedx_course_id': course_id, 'total': 0, 'updated': 0, 'processed': 0, 'verified': 0, 'counts': {}, 'message': 'Không có sinh viên/giảng viên cần xử lý Course CMS', 'learning_summary': summary, 'teachers': {'total': 0, 'updated': 0, 'processed': 0, 'verified': 0, 'counts': {}}}
        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
        counts: dict[str, int] = {}
        processed = 0
        updated = 0
        verified = 0
        failed_messages: list[str] = []
        teacher_counts: dict[str, int] = {}
        teacher_processed = 0
        teacher_updated = 0
        teacher_verified = 0
        enrollment_mode = (mode or getattr(settings, 'openedx_connector_default_enrollment_mode', getattr(settings, 'openedx_student_insight_default_enrollment_mode', 'audit')) or 'audit').strip() or 'audit'
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
                snapshot = self._upsert_enrollment_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_connector_enrollment')
                raw_status = str(result.get('status') or result.get('enrollment_status') or snapshot.enrollment_status or 'unknown').strip().lower()
                is_enrolled = _boolish(result.get('is_enrolled')) or str(result.get('enrollment_status') or '').strip().lower() == 'enrolled'
                status_value = 'enrolled' if is_enrolled else raw_status
                counts[status_value] = counts.get(status_value, 0) + 1
                processed += 1
                if is_enrolled:
                    updated += 1
                    if result.get('verified_after_write') is not False:
                        verified += 1
                else:
                    message = str(result.get('message') or '').strip()
                    if message and len(failed_messages) < 5:
                        failed_messages.append(f"{student.username}: {message}")
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
                        **_json_safe_value(existing),
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
                    teacher_success = status_value in {'already_course_staff', 'course_staff_added'} or str(result.get('course_role') or '').strip().lower() == 'staff'
                    teacher_counts[status_value] = teacher_counts.get(status_value, 0) + 1
                    counts[f'teacher_{status_value}'] = counts.get(f'teacher_{status_value}', 0) + 1
                    teacher_processed += 1
                    if teacher_success:
                        teacher_updated += 1
                        if result.get('verified_after_write') is not False:
                            teacher_verified += 1
                    else:
                        message = str(result.get('message') or '').strip()
                        if message and len(failed_messages) < 5:
                            failed_messages.append(f"GV {username}: {message}")
                self.db.flush()

        if rows and updated == 0:
            self.db.commit()
            detail = '; '.join(failed_messages) if failed_messages else f"counts={counts}"
            raise RuntimeError(f'Enrollment Course CMS không có sinh viên nào được xác nhận enrolled trên Open edX sau khi gọi connector. {detail}')

        self.db.commit()
        summary = self._learning_summary_for_class_course(class_id, course_id)
        return {
            'ok': True,
            'class_id': class_id,
            'openedx_course_id': course_id,
            'total': len(rows),
            'processed': processed,
            'updated': updated,
            'verified': verified,
            'counts': counts,
            'message': f'Enrollment Course CMS hoàn tất: {updated}/{len(rows)} sinh viên được Open edX xác nhận enrolled; {teacher_updated}/{len(teacher_payload)} giảng viên được gán Course Staff.',
            'learning_summary': summary,
            'teachers': {'total': len(teacher_payload), 'processed': teacher_processed, 'updated': teacher_updated, 'verified': teacher_verified, 'counts': teacher_counts},
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
        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
        updated = 0
        connector_enrolled_seen = 0
        connector_progress_seen = 0
        connector_grade_seen = 0
        connector_component_seen = 0
        connector_missing_result = 0
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
                    connector_missing_result += 1
                    result = {
                        'student_code': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': key,
                        'enrollment_status': 'unknown',
                        'note': 'Plugin không trả dữ liệu học tập cho sinh viên này',
                    }
                enrollment_payload = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
                enrollment_status_raw = str(result.get('enrollment_status') or enrollment_payload.get('status') or '').strip().lower()
                if enrollment_status_raw in {'enrolled', 'already_enrolled', 'created', 'reactivated'} or _boolish(result.get('is_enrolled')) or enrollment_payload.get('is_enrolled') is True:
                    connector_enrolled_seen += 1
                progress_payload = result.get('progress') if isinstance(result.get('progress'), dict) else {}
                grade_payload = result.get('grade') if isinstance(result.get('grade'), dict) else {}
                if result.get('progress_percent') is not None or progress_payload.get('percent') is not None or result.get('completed_blocks') is not None or progress_payload.get('completed_blocks') is not None:
                    connector_progress_seen += 1
                if result.get('grade_percent') is not None or grade_payload.get('percent') is not None:
                    connector_grade_seen += 1
                if self._component_scores_from_payload(result):
                    connector_component_seen += 1
                self._upsert_learning_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_connector')
                updated += 1
            self.db.flush()
        self.db.commit()
        if updated > 0 and connector_enrolled_seen <= 0:
            raise RuntimeError('Cập nhật tiến độ/điểm không có sinh viên nào được connector xác nhận enrolled trên Open edX. Hãy chạy lại Enrollment Course CMS và kiểm tra CourseEnrollment trước khi lấy điểm.')
        summary = self._learning_summary_for_class_course(class_id, course_id)
        connector_counts = {
            'checked': int(updated),
            'enrolled_seen': int(connector_enrolled_seen),
            'with_progress': int(connector_progress_seen),
            'with_total_grade': int(connector_grade_seen),
            'with_component_grades': int(connector_component_seen),
            'missing_result': int(connector_missing_result),
        }
        if connector_grade_seen or connector_component_seen or connector_progress_seen:
            message = f'Đã cập nhật tiến độ/điểm CMS cho lớp: enrolled {connector_enrolled_seen}/{updated}, progress {connector_progress_seen}, điểm tổng {connector_grade_seen}, điểm thành phần {connector_component_seen}.'
        else:
            message = f'Đã kiểm tra học tập CMS: {connector_enrolled_seen}/{updated} sinh viên đã enrolled nhưng Open edX chưa có progress/grade/subsection grade để hiển thị.'
        return {'ok': True, 'updated': updated, 'connector_counts': connector_counts, 'message': message, **summary}


    def _try_auto_map_course_for_class(self, user: UserContext, cls: AcademicClass) -> dict[str, Any]:
        """Best-effort safe course mapping for full Student Progress sync.

        It only creates a subject-term mapping when CMS/Open edX API returns one safe candidate for the subject + term. It never creates a fake Course CMS and never creates accounts before mapping exists.
        """
        current = self.effective_course_mapping_for_class(cls)
        if current and current.openedx_course_id:
            return {
                'ok': True,
                'status': 'already_mapped',
                'openedx_course_id': current.openedx_course_id,
                'mapping_source': 'class_override' if isinstance(current, AcademicClassCourseMapping) else 'subject_term_mapping',
                'mapping': self._class_course_mapping_item(current) if isinstance(current, AcademicClassCourseMapping) else self._course_mapping_item(current),
                'message': 'Lớp đã có Course CMS mapping.',
            }
        if not getattr(settings, 'academic_auto_map_course_before_cms_sync', True):
            return {'ok': False, 'status': 'mapping_required', 'openedx_course_id': None, 'mapping': None, 'message': 'Lớp chưa có Course CMS mapping.'}
        subject = self.db.get(AcademicSubject, cls.subject_id)
        if not subject:
            return {'ok': False, 'status': 'subject_missing', 'openedx_course_id': None, 'mapping': None, 'message': 'Không tìm thấy môn AP để auto-map Course CMS.'}
        branch_value = (cls.branch or subject.branch or '').strip().lower() or None
        suggested = self.suggested_course_id_for_scope(cls.term_id, cls.subject_id)
        lookup = self._find_openedx_course_candidate_for_scope(term=self.db.get(AcademicTerm, cls.term_id), subject=subject, suggested=suggested, allow_external=True)
        candidate = lookup.get('candidate')
        count = int(lookup.get('count') or 0)
        title = lookup.get('title')
        source = str(lookup.get('source') or 'cms_openedx_api')
        if count != 1 or not candidate:
            status_value = 'course_not_found' if count == 0 else 'multiple_course_candidates'
            return {
                'ok': False,
                'status': status_value,
                'openedx_course_id': None,
                'suggested_openedx_course_id': suggested,
                'candidate_count': count,
                'candidate_source': source,
                'candidates': lookup.get('candidates') or [],
                'mapping': None,
                'message': 'Chưa tìm thấy đúng một Course CMS khớp mã môn/kỳ qua API CMS/Open edX. Chưa tạo tài khoản CMS; hãy kiểm tra kết nối API CMS/Open edX hoặc map Course CMS thủ công trước khi chạy tạo user/enroll/lấy điểm.',
            }
        mapping = self._auto_create_subject_course_mapping_if_safe(
            user,
            term_id=cls.term_id,
            subject_id=cls.subject_id,
            branch_value=branch_value,
            candidate=candidate,
            suggested=suggested,
            openedx_course_title=title,
            candidate_source=source,
            commit=True,
        )
        if not mapping:
            return {'ok': False, 'status': 'mapping_validation_failed', 'openedx_course_id': None, 'suggested_openedx_course_id': suggested, 'mapping': None, 'message': 'Course CMS khớp mã nhưng không đạt điều kiện mapping an toàn.'}
        return {
            'ok': True,
            'status': 'auto_mapped',
            'openedx_course_id': mapping.openedx_course_id,
            'suggested_openedx_course_id': suggested,
            'mapping': self._course_mapping_item(mapping),
            'message': 'Đã tự động map môn/kỳ với Course CMS khớp chính xác.',
        }

    def sync_class_full_cms_flow(
        self,
        user: UserContext,
        class_id: str,
        *,
        force: bool = False,
        limit: int = 1000,
        mode: str | None = None,
        auto_map_course: bool = True,
        sync_learning: bool = True,
    ) -> dict[str, Any]:
        """Run the production Student Progress flow for a class.

        Order is intentionally strict and map-first:
          1. Resolve or safely auto-map Course CMS.
          2. If Course CMS is still missing, stop without creating CMS accounts.
          3. Resolve/create CMS accounts from AP usernames only after mapping exists.
          4. Enroll learners and add teachers as Course Staff.
          5. Pull progress, total grade and component/quiz grades.
        """
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        limit = max(1, min(500, int(limit or 500)))
        counts: dict[str, int] = {}

        mapping_result = self._try_auto_map_course_for_class(user, cls) if auto_map_course else {'ok': False, 'status': 'mapping_required', 'openedx_course_id': None, 'mapping': None, 'message': 'Auto-map Course CMS bị tắt cho lần chạy này.'}
        mapping = self.effective_course_mapping_for_class(cls)
        course_id = mapping.openedx_course_id if mapping else None
        if not course_id:
            return {
                'ok': True,
                'class_id': class_id,
                'openedx_course_id': None,
                'status': 'mapping_required_no_cms_user_created',
                'message': 'Lớp chưa map Course CMS nên hệ thống chưa tạo tài khoản CMS, chưa enroll và chưa lấy điểm. Hãy map Course CMS trước rồi chạy lại Đồng bộ full CMS.',
                'mapping': mapping_result,
                'cms_users': None,
                'enrollment': None,
                'learning': None,
                'counts': counts,
                'learning_summary': self._learning_summary_for_class_course(class_id, None),
            }

        cms_result = self.resolve_class_openedx_users(user, class_id, force=True if force else False, limit=limit, auto_enroll=False)
        for key, value in (cms_result.get('counts') or {}).items():
            counts[f'cms_{key}'] = int(value or 0)
        teacher_counts = ((cms_result.get('teachers') or {}).get('counts') or {}) if isinstance(cms_result.get('teachers'), dict) else {}
        for key, value in teacher_counts.items():
            counts[f'teacher_cms_{key}'] = int(value or 0)

        enrollment_result = self.sync_class_course_enrollment(user, class_id, force=force, limit=limit, mode=mode)
        for key, value in (enrollment_result.get('counts') or {}).items():
            counts[f'enrollment_{key}'] = int(value or 0)
        enroll_teacher_counts = ((enrollment_result.get('teachers') or {}).get('counts') or {}) if isinstance(enrollment_result.get('teachers'), dict) else {}
        for key, value in enroll_teacher_counts.items():
            counts[f'teacher_enrollment_{key}'] = int(value or 0)

        learning_result = None
        if sync_learning and getattr(settings, 'academic_full_sync_learning_after_enrollment', True):
            learning_result = self.sync_class_learning_insight(user, class_id, force=force, limit=limit)
            for key, value in (learning_result.get('counts') or {}).items():
                counts[f'learning_{key}'] = int(value or 0)

        summary = self._learning_summary_for_class_course(class_id, course_id)
        message = 'Full CMS sync hoàn tất: đã tạo/kiểm tra user CMS, enroll Course CMS và cập nhật tiến độ/điểm.' if learning_result else 'Full CMS sync hoàn tất: đã tạo/kiểm tra user CMS và enroll Course CMS.'
        return {
            'ok': True,
            'class_id': class_id,
            'openedx_course_id': course_id,
            'status': 'completed',
            'message': message,
            'mapping': mapping_result,
            'cms_users': cms_result,
            'enrollment': enrollment_result,
            'learning': learning_result,
            'counts': counts,
            'learning_summary': summary,
        }


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

