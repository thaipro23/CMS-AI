from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from uuid import UUID
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.core.timezone import VN_TZ, to_vn_date, to_vn_naive_datetime
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
    AcademicTeacherReportSummary,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.business_rbac import BusinessRBACService
from app.services.openedx_student_insight import OpenEdXConnectorClient, normalize_username, mask_email
from app.services.training_policy_service import TrainingPolicyService
from app.core.config import settings
from app.core.json_safe import json_safe_value
from app.models.course import CourseSyncState
from app.models.question_bank import Subject as BankSubject


from app.services.academic.helpers import (
    AccessDecision,
    _actor_names,
    _boolish,
    _check,
    _clean_token,
    _derive_mapping_status,
    _json_safe_value,
    _natural_sort_key,
    _normalize_text_key,
    _page,
    _parse_openedx_course_id,
    _safe_mapping_raw,
    _suggest_course_run,
    _term_run_candidates,
    _validation_result,
)

from app.services.academic.access import AcademicAccessWorkflowService
from app.services.academic.roster import AcademicRosterWorkflowService
from app.services.academic.sync_enrollment import AcademicSyncEnrollmentWorkflowService
from app.services.academic.identity import AcademicIdentityReconciliationWorkflowService
from app.services.academic.teacher_report import AcademicTeacherReportWorkflowService
class AcademicService:
    CONNECTOR_MIN_CONTRACT_VERSION = 'learning-sync/v25.9.16.5.98'
    CONNECTOR_MIN_RUNTIME_VERSION = '25.9.16.5.98'

    def __init__(self, db: Session):
        self.db = db
        self.rbac = BusinessRBACService(db)

    def _academic_sync_enrollment_workflow(self) -> AcademicSyncEnrollmentWorkflowService:
        return AcademicSyncEnrollmentWorkflowService(self.db, self)

    def _academic_identity_workflow(self) -> AcademicIdentityReconciliationWorkflowService:
        return AcademicIdentityReconciliationWorkflowService(self.db, self)

    @staticmethod
    def _version_tuple(value: Any) -> tuple[int, ...]:
        parts = []
        for token in re.findall(r'\d+', str(value or '')):
            try:
                parts.append(int(token))
            except Exception:
                parts.append(0)
        return tuple(parts or [0])

    @classmethod
    def _version_at_least(cls, actual: Any, expected: Any) -> bool:
        a = list(cls._version_tuple(actual))
        e = list(cls._version_tuple(expected))
        width = max(len(a), len(e))
        a.extend([0] * (width - len(a)))
        e.extend([0] * (width - len(e)))
        return tuple(a) >= tuple(e)

    def _validate_connector_learning_contract(self, payload: dict[str, Any], *, course_id: str) -> None:
        """Fail fast when LMS connector is too old or returns unsafe completion contract.

        This prevents an older connector from writing `NULL`, raw StudentModule row
        counts, or the old 70-block denominator over good snapshots.
        """
        if not isinstance(payload, dict):
            raise RuntimeError('Open edX Connector class-analytics trả về payload không hợp lệ')
        if payload.get('ok') is False:
            raise RuntimeError(str(payload.get('message') or payload.get('detail') or 'Open edX Connector báo lỗi khi lấy dữ liệu học tập'))
        version = payload.get('connector_version') or (payload.get('diagnostics') or {}).get('connector_version')
        contract = payload.get('connector_contract_version') or (payload.get('diagnostics') or {}).get('connector_contract_version')
        progress_contract = payload.get('progress_contract') if isinstance(payload.get('progress_contract'), dict) else {}
        if not version or not self._version_at_least(version, self.CONNECTOR_MIN_RUNTIME_VERSION):
            raise RuntimeError(
                f'Open edX Connector đang thiếu hoặc cũ hơn {self.CONNECTOR_MIN_RUNTIME_VERSION} cho Course {course_id}. '
                'Hãy cập nhật plugin, restart lms/cms/lms-worker/cms-worker, rồi kiểm tra CONNECTOR_VERSION trước khi Cập nhật điểm.'
            )
        if contract and str(contract) != self.CONNECTOR_MIN_CONTRACT_VERSION:
            raise RuntimeError(
                f'Open edX Connector contract không khớp ({contract}). Yêu cầu {self.CONNECTOR_MIN_CONTRACT_VERSION}. '
                'Dừng ghi snapshot để tránh ghi đè dữ liệu đúng bằng payload sai contract.'
            )
        if not progress_contract:
            raise RuntimeError('Open edX Connector không trả progress_contract. Dừng sync để tránh dùng lại rule completion cũ.')
        denominator = str(progress_contract.get('denominator') or '')
        numerator = str(progress_contract.get('numerator') or '')
        ignored = {str(item).lower() for item in (progress_contract.get('ignored_studentmodule_types') or [])}
        if denominator != 'reachable_sequential_subsections' or numerator != 'studentmodule_sequential_position_rows' or 'itembank' not in ignored:
            raise RuntimeError(
                'Open edX Connector progress_contract không an toàn. Yêu cầu denominator=reachable_sequential_subsections, '
                'numerator=studentmodule_sequential_position_rows và phải bỏ itembank/problem/video khỏi Course completion.'
            )

    def _invalidate_teacher_report_cache_for_class(self, class_id: str, *, reason: str) -> int:
        """Invalidate teacher report materialized rows affected by one class.

        Deleting scoped cache is safer than trying to patch aggregate rows. The next
        teacher-management request falls back to live data or the operator rebuilds
        the report job.
        """
        cls = self.db.get(AcademicClass, class_id)
        if not cls or not cls.term_id:
            return 0
        branch = str(cls.branch or '').strip().lower()
        campus = str(cls.campus or '').strip().lower()
        query = self.db.query(AcademicTeacherReportSummary).filter(AcademicTeacherReportSummary.term_id == cls.term_id)
        if branch:
            query = query.filter(or_(AcademicTeacherReportSummary.branch.is_(None), func.lower(AcademicTeacherReportSummary.branch) == branch))
        if campus:
            query = query.filter(or_(AcademicTeacherReportSummary.campus.is_(None), func.lower(AcademicTeacherReportSummary.campus) == campus))
        deleted = query.delete(synchronize_session=False)
        return int(deleted or 0)

    def _access_workflow(self) -> AcademicAccessWorkflowService:
        return AcademicAccessWorkflowService(self.db, self.rbac)

    def access_decision(self, user: UserContext) -> AccessDecision:
        # Bank roles
        # (DEPARTMENT_HEAD/SUBJECT_OWNER/QUESTION_REVIEWER) no longer grant
        # AP class/student analytics visibility. Student Ops visibility is
        # delegated to AcademicAccessWorkflowService and comes only from
        # campus-scoped roles and AP teacher assignments.
        return self._access_workflow().access_decision(user)

    def assert_can_access_class(self, user: UserContext, class_id: str) -> None:
        return self._access_workflow().assert_can_access_class(user, class_id)

    def assert_can_access_subject(self, user: UserContext, subject_id: str) -> None:
        return self._access_workflow().assert_can_access_subject(user, subject_id)

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
        term.start_date = to_vn_naive_datetime(payload.get('start_date'))
        term.end_date = to_vn_naive_datetime(payload.get('end_date'))
        term.active = _boolish(payload.get('active')) is not False
        meta = dict(term.metadata_json or {})
        if isinstance(payload.get('metadata_json'), dict):
            meta.update(payload.get('metadata_json') or {})
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
            block.start_date = to_vn_naive_datetime(raw_block.get('start_date'))
            block.end_date = to_vn_naive_datetime(raw_block.get('end_date'))
            block.sort_order = int(raw_block.get('sort_order') or index)
            block.active = _boolish(raw_block.get('active')) is not False
            block_meta = dict(block.metadata_json or {})
            if isinstance(raw_block.get('metadata_json'), dict):
                block_meta.update(raw_block.get('metadata_json') or {})
            if isinstance(block_meta.get('learning_weeks'), list):
                normalized_weeks: list[dict[str, Any]] = []
                for week in block_meta.get('learning_weeks') or []:
                    if not isinstance(week, dict):
                        continue
                    start_dt = to_vn_naive_datetime(week.get('start_date') or week.get('from_date') or week.get('from'))
                    end_dt = to_vn_naive_datetime(week.get('end_date') or week.get('to_date') or week.get('to') or week.get('deadline_date'))
                    if not start_dt or not end_dt:
                        continue
                    normalized_weeks.append({
                        **week,
                        'week_number': int(week.get('week_number') or len(normalized_weeks) + 1),
                        'start_date': start_dt.isoformat(),
                        'end_date': end_dt.isoformat(),
                    })
                block_meta['learning_weeks'] = normalized_weeks
            block_meta.update({'source': block_meta.get('source') or 'manual_ui', 'updated_from': 'terms_page', 'timezone': 'Asia/Ho_Chi_Minh'})
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
        teacher_id: str | None = None,
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
            if decision.campus_codes:
                access_conditions.append(func.lower(AcademicClass.campus).in_(decision.campus_codes))
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
            query = query.filter(func.lower(AcademicClass.branch) == branch.strip().lower())
        if campus:
            campus_code = self._campus_filter_value(campus)
            query = query.filter(func.lower(AcademicClass.campus) == campus_code)
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
        # Production rule: management KPI cards must be calculated from the full current filter,
        # not from the current page. The previous page-only aggregate made a subject opened as
        # "Tất cả cơ sở" shrink to one campus after returning from class detail. Keep the page
        # small for rendering, but compute totals from all filtered classes.
        rows = ordered.all()
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
            filtered_items = [entry for entry in items if self._entry_matches_learning_list_filter(entry, status_filter)]
        else:
            filtered_items = items
        total = len(filtered_items)
        total_pages = math.ceil(total / page_size) if total else 0
        page_items = filtered_items[(page - 1) * page_size:page * page_size]
        summary = {
            'class_count': int(total),
            'student_count': int(sum(int(item.get('student_count') or 0) for item in filtered_items)),
            'cms_synced_count': int(sum(int(item.get('cms_synced_count') or 0) for item in filtered_items)),
            'cms_unsynced_count': int(sum(int(item.get('cms_unsynced_count') or 0) for item in filtered_items)),
            'learning_enrolled_count': int(sum(int(item.get('learning_enrolled_count') or 0) for item in filtered_items)),
            'learning_synced_count': int(sum(int(item.get('learning_synced_count') or 0) for item in filtered_items)),
            'learning_active_count': int(sum(int(item.get('learning_active_count') or 0) for item in filtered_items)),
            'course_mapped_count': int(sum(1 for item in filtered_items if item.get('openedx_course_id'))),
            'course_missing_count': int(sum(1 for item in filtered_items if not item.get('openedx_course_id'))),
            'alert_class_count': int(sum(1 for item in filtered_items if item.get('learning_alerts'))),
            'scope_label': 'Toàn bộ bộ lọc',
        }
        return {'items': page_items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages, 'summary': summary}

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
        if decision.campus_codes:
            access_conditions.append(func.lower(AcademicClass.campus).in_(decision.campus_codes))
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
            query = query.filter(func.lower(AcademicClass.campus) == campus.strip().lower())
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
            incomplete = self._number_or_none(
                value.get('incomplete_blocks')
                or value.get('incomplete_count')
                or value.get('incomplete')
                or value.get('not_completed')
                or value.get('remaining')
                or value.get('todo')
            )
            if completed is not None and incomplete is not None and completed + incomplete > 0:
                return round((completed / (completed + incomplete)) * 100.0, 2)
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


    def _progress_payload_sources(self, payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(payload, dict):
            return []
        candidates: list[Any] = [payload.get('progress_source'), payload.get('progressSource'), payload.get('source')]
        progress = payload.get('progress') if isinstance(payload.get('progress'), dict) else None
        if progress:
            candidates.extend([
                progress.get('source'),
                progress.get('progress_source'),
                progress.get('progressSource'),
                progress.get('student_module_source'),
                progress.get('fallback_reason'),
            ])
        values: list[str] = []
        for raw in candidates:
            text = str(raw or '').strip()
            if text:
                values.append(text)
        return values

    def _is_official_progress_payload(self, payload: dict[str, Any] | None) -> bool:
        for raw in self._progress_payload_sources(payload):
            text = raw.replace('_', '').replace('-', '').replace(' ', '').lower()
            if (
                text in {'coursehomeapi', 'coursehome', 'courseprogressapi', 'learnerdashboard', 'official', 'completionapi', 'coursecompletionapi'}
                or 'coursehome' in text
                or 'completionapi' in text
                or 'courseprogress' in text
            ):
                return True
        return False

    def _is_student_module_progress_payload(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        progress = payload.get('progress') if isinstance(payload.get('progress'), dict) else {}
        if payload.get('progress_source') == 'StudentModule' or progress.get('source') == 'StudentModule':
            return True
        if progress.get('has_student_module_fallback') is True or payload.get('has_student_module_fallback') is True:
            return True
        for raw in self._progress_payload_sources(payload):
            text = raw.replace('_', '').replace('-', '').replace(' ', '').lower()
            if 'studentmodule' in text or 'studentmodulecounts' in text:
                return True
        return False

    def _has_accepted_progress_payload(self, payload: dict[str, Any] | None) -> bool:
        return self._is_official_progress_payload(payload) or self._is_student_module_progress_payload(payload)

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
            completed = self._number_or_none(container.get('completed_blocks') or container.get('complete_count') or container.get('completed_count') or container.get('completed') or container.get('complete') or container.get('done') or container.get('visited'))
            total = self._number_or_none(container.get('total_blocks') or container.get('total_count') or container.get('block_count') or container.get('total') or container.get('required'))
            if completed is not None and total and total > 0:
                return round((completed / total) * 100.0, 2)
            incomplete = self._number_or_none(container.get('incomplete_blocks') or container.get('incomplete_count') or container.get('incomplete') or container.get('not_completed') or container.get('remaining'))
            if completed is not None and incomplete is not None and completed + incomplete > 0:
                return round((completed / (completed + incomplete)) * 100.0, 2)
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
        if not self._has_accepted_progress_payload(payload):
            return None
        direct = self._percent_display_value(snapshot.progress_percent)
        if direct is not None:
            return direct
        return self._progress_percent_from_payload(payload)

    def _snapshot_progress_source(self, snapshot: AcademicStudentLearningSnapshot | None) -> str | None:
        if not snapshot:
            return None
        payload = self._payload_from_snapshot(snapshot)
        progress = payload.get('progress') if isinstance(payload.get('progress'), dict) else None
        for value in (
            payload.get('progress_source'),
            payload.get('progressSource'),
            progress.get('source') if progress else None,
            progress.get('progress_source') if progress else None,
            progress.get('progressSource') if progress else None,
        ):
            text = str(value or '').strip()
            if text:
                return text[:120]
        if snapshot.completed_blocks is not None or snapshot.total_blocks is not None:
            return 'diagnostic_counts_only'
        return None

    def _snapshot_grade_percent(self, snapshot: AcademicStudentLearningSnapshot | None) -> float | None:
        if not snapshot:
            return None
        direct = self._percent_display_value(snapshot.grade_percent)
        if direct is not None:
            return direct
        return self._grade_percent_from_payload(self._payload_from_snapshot(snapshot))

    def _learning_snapshot_diagnostics(self, snapshot: AcademicStudentLearningSnapshot | None, mapping: OpenEdXUserMapping | None = None) -> dict[str, Any]:
        """Explain the state of one learner's CMS learning snapshot.

        This is intentionally diagnostic metadata, not business policy. It lets
        the UI distinguish between real learning risk and data-quality issues
        such as the connector not returning Course Home progress.
        """
        if mapping is None or (mapping.match_status or '') != 'matched':
            return {
                'status': 'cms_not_synced',
                'severity': 'blocking',
                'note': 'Chưa match được user CMS theo AP username nên chưa thể lấy enrollment/progress/grade.',
                'official_progress': False,
                'has_progress_percent': False,
                'has_grade_percent': False,
                'has_component_grades': False,
                'progress_source': None,
            }
        if not snapshot:
            return {
                'status': 'not_synced',
                'severity': 'warning',
                'note': 'Chưa có snapshot học tập. Chạy Cập nhật điểm để đọc Course completion/grade từ Open edX.',
                'official_progress': False,
                'has_progress_percent': False,
                'has_grade_percent': False,
                'has_component_grades': False,
                'progress_source': None,
            }
        payload = self._payload_from_snapshot(snapshot)
        source = self._snapshot_progress_source(snapshot)
        official = self._is_official_progress_payload(payload)
        student_module = self._is_student_module_progress_payload(payload)
        progress = self._snapshot_progress_percent(snapshot)
        grade = self._snapshot_grade_percent(snapshot)
        components = self._component_scores_from_snapshot(snapshot)
        enrollment_status = str(snapshot.enrollment_status or 'unknown').lower()
        notes: list[str] = []
        severity = 'ok'
        if enrollment_status != 'enrolled':
            severity = 'blocking'
            notes.append(f'Enrollment CMS hiện là {enrollment_status}; cần Đồng bộ full CMS để enroll trước khi đọc điểm ổn định.')
        progress_payload = payload.get('progress') if isinstance(payload.get('progress'), dict) else {}
        sm_raw_rows = self._int_or_none(progress_payload.get('student_module_raw_rows') or payload.get('student_module_raw_rows'))
        sm_activity_blocks = self._int_or_none(progress_payload.get('student_module_activity_blocks') or payload.get('student_module_activity_blocks') or progress_payload.get('student_module_completed_blocks') or payload.get('student_module_completed_blocks'))
        sm_ignored_rows = self._int_or_none(progress_payload.get('student_module_ignored_rows') or payload.get('student_module_ignored_rows'))
        sm_rule = str(progress_payload.get('student_module_fallback_rule') or payload.get('student_module_fallback_rule') or '').strip()
        if not official and not student_module:
            severity = 'warning' if severity == 'ok' else severity
            notes.append('Connector chưa trả Course Home Progress official hoặc StudentModule fallback; Course completion sẽ hiển thị N/A thay vì đoán từ quiz/subsection.')
        elif student_module and not official:
            if progress is None:
                severity = 'warning' if severity == 'ok' else severity
                notes.append('Connector trả StudentModule nhưng thiếu completed_blocks/total_blocks nên chưa tính được Course completion fallback.')
            else:
                detail = ''
                if sm_raw_rows is not None or sm_activity_blocks is not None or sm_ignored_rows is not None:
                    detail = f" StudentModule raw={sm_raw_rows if sm_raw_rows is not None else 'N/A'}, activity={sm_activity_blocks if sm_activity_blocks is not None else 'N/A'}, ignored={sm_ignored_rows if sm_ignored_rows is not None else 'N/A'}."
                rule = ' Chỉ tính activity rows, không tính row container/state rỗng; từ v88 mẫu số chỉ lấy leaf learning components đang reachable trong LMS.' if sm_rule == 'activity_rows_only_excluding_empty_container_rows' else ''
                notes.append('Course completion đang dùng fallback StudentModule = completed_blocks / total_blocks.' + detail + rule + ' Nên restart LMS sau khi cập nhật connector để kiểm tra lại Course Home Progress official.')
        elif progress is None:
            severity = 'warning' if severity == 'ok' else severity
            notes.append('Có source official nhưng chưa parse được Course completion percent.')
        if grade is None:
            notes.append('Open edX chưa trả điểm tổng course_grade/final_grades.')
        if not components:
            notes.append('Open edX chưa trả detailed grades/section scores cho các đầu điểm.')
        if not notes:
            notes.append('Snapshot học tập có source/progress/grade đủ để hiển thị.')
        return {
            'status': self._learning_status_for_snapshot(snapshot, mapping),
            'severity': severity,
            'note': ' '.join(notes)[:1000],
            'official_progress': bool(official),
            'student_module_progress': bool(student_module),
            'has_progress_percent': progress is not None,
            'completed_blocks': getattr(snapshot, 'completed_blocks', None),
            'total_blocks': getattr(snapshot, 'total_blocks', None),
            'student_module_raw_rows': sm_raw_rows,
            'student_module_activity_blocks': sm_activity_blocks,
            'student_module_ignored_rows': sm_ignored_rows,
            'student_module_fallback_rule': sm_rule or None,
            'has_grade_percent': grade is not None,
            'has_component_grades': bool(components),
            'progress_source': source,
            'last_synced_at': (snapshot.learning_synced_at or snapshot.last_synced_at).isoformat() if (snapshot.learning_synced_at or snapshot.last_synced_at) else None,
        }

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
        return to_vn_date(value)

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
        explicit = self._number_or_none(item.get('quiz_number') or item.get('quizNumber'))
        if explicit is not None and 1 <= int(explicit) <= 200:
            return [int(explicit)]

        # Only parse human-facing labels here. Do not parse usage keys such as
        # `block@quiz-14-...`: those are storage identifiers and created phantom
        # columns like `Quiz 14` even when CMS had only 2 real Quiz subsections.
        label_text = ' '.join(str(item.get(key) or '') for key in ('name', 'label', 'display_name', 'title'))
        numbers = self._quiz_numbers_from_text(label_text)
        if numbers:
            return numbers

        category = str(item.get('category') or '').strip().lower()
        name = str(item.get('name') or item.get('label') or '').strip().lower()
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


    def _learning_week_schedule_from_block(self, block: AcademicBlock | None) -> list[dict[str, Any]]:
        """Return week schedule configured in /semesters.

        Stored in AcademicBlock.metadata_json.learning_weeks as dd/mm/yyyy-friendly
        week ranges. This is the source of truth for quiz deadline allocation when
        the academic calendar is shifted by holidays; class detail refresh and full
        CMS sync both reload this via DB.
        """
        if not block or not isinstance(block.metadata_json, dict):
            return []
        raw_weeks = block.metadata_json.get('learning_weeks') or block.metadata_json.get('week_schedule') or []
        if not isinstance(raw_weeks, list):
            return []
        weeks: list[dict[str, Any]] = []
        for idx, raw in enumerate(raw_weeks, start=1):
            if not isinstance(raw, dict):
                continue
            start = self._date_only(raw.get('start_date') or raw.get('from_date') or raw.get('from'))
            end = self._date_only(raw.get('end_date') or raw.get('to_date') or raw.get('to') or raw.get('deadline_date'))
            if not start or not end:
                continue
            weeks.append({
                'week_number': int(raw.get('week_number') or idx),
                'from_date': start.isoformat(),
                'due_date': end.isoformat(),
                'label': str(raw.get('label') or f'Tuần {idx}'),
                'source': 'semester_week_config',
            })
        weeks.sort(key=lambda item: int(item.get('week_number') or 0))
        return weeks

    def _quiz_deadline_schedule_from_weeks(self, quiz_count: int, weeks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        quiz_count = max(0, int(quiz_count or 0))
        valid_weeks = [item for item in weeks or [] if item.get('from_date') and item.get('due_date')]
        if quiz_count <= 0 or not valid_weeks:
            return []
        week_count = len(valid_weeks)
        schedule: list[dict[str, Any]] = []
        if quiz_count <= week_count:
            base_weeks = week_count // quiz_count
            remainder_weeks = week_count % quiz_count
            cursor = 0
            for quiz_number in range(1, quiz_count + 1):
                span = base_weeks + (1 if quiz_number <= remainder_weeks else 0)
                chunk = valid_weeks[cursor:cursor + span]
                if not chunk:
                    break
                schedule.append({
                    'week_number': chunk[0].get('week_number') or cursor + 1,
                    'week_to_number': chunk[-1].get('week_number') or cursor + span,
                    'label': f'Quiz {quiz_number}',
                    'quiz_numbers': [quiz_number],
                    'from_date': chunk[0]['from_date'],
                    'due_date': chunk[-1]['due_date'],
                    'source': 'semester_week_config',
                })
                cursor += span
            return schedule
        base = quiz_count // week_count
        remainder = quiz_count % week_count
        quiz_number = 1
        for index, week in enumerate(valid_weeks):
            count = base + (1 if index < remainder else 0)
            if count <= 0:
                continue
            numbers = list(range(quiz_number, quiz_number + count))
            quiz_number += count
            schedule.append({
                'week_number': week.get('week_number') or index + 1,
                'label': f"Quiz {numbers[0]}" if len(numbers) == 1 else f"Quiz {numbers[0]}-{numbers[-1]}",
                'quiz_numbers': numbers,
                'from_date': week['from_date'],
                'due_date': week['due_date'],
                'source': 'semester_week_config',
            })
        return schedule

    @staticmethod
    def _quiz_deadline_schedule(quiz_count: int, block_start: date | None) -> list[dict[str, Any]]:
        quiz_count = max(0, int(quiz_count or 0))
        if quiz_count <= 0 or not block_start:
            return []
        # Một block học 7 tuần: 6 tuần đầu dành deadline quiz, tuần 7 là Ôn+Thi.
        # Khi số Quiz ít hơn 6, chia đều **thời lượng học** cho từng Quiz.
        # Ví dụ 2 Quiz => Quiz 1 hết tuần 3, Quiz 2 hết tuần 6; không dồn cả hai vào tuần 1.
        quiz_weeks = 6
        schedule: list[dict[str, Any]] = []
        if quiz_count <= quiz_weeks:
            base_weeks = quiz_weeks // quiz_count
            remainder_weeks = quiz_weeks % quiz_count
            week_cursor = 0
            for quiz_number in range(1, quiz_count + 1):
                span = base_weeks + (1 if quiz_number <= remainder_weeks else 0)
                from_date = block_start + timedelta(days=week_cursor * 7)
                due_date = block_start + timedelta(days=(week_cursor + span - 1) * 7 + 5)  # T2 -> T7 của tuần cuối được phân bổ
                schedule.append({
                    'week_number': week_cursor + 1,
                    'week_to_number': week_cursor + span,
                    'label': f'Quiz {quiz_number}',
                    'quiz_numbers': [quiz_number],
                    'from_date': from_date.isoformat(),
                    'due_date': due_date.isoformat(),
                })
                week_cursor += span
            return schedule

        # Khi số Quiz nhiều hơn 6, chia số Quiz theo từng tuần, phần dư dồn vào các tuần đầu.
        base = quiz_count // quiz_weeks
        remainder = quiz_count % quiz_weeks
        quiz_number = 1
        for week_index in range(quiz_weeks):
            week_quiz_count = base + (1 if week_index < remainder else 0)
            if week_quiz_count <= 0:
                continue
            from_date = block_start + timedelta(days=week_index * 7)
            due_date = from_date + timedelta(days=5)  # T2 -> T7
            quiz_numbers = list(range(quiz_number, quiz_number + week_quiz_count))
            quiz_number += week_quiz_count
            label = f"Quiz {quiz_numbers[0]}" if len(quiz_numbers) == 1 else f"Quiz {quiz_numbers[0]}-{quiz_numbers[-1]}"
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
        configured_weeks = self._learning_week_schedule_from_block(block)
        schedule_items = self._quiz_deadline_schedule_from_weeks(quiz_count, configured_weeks) if configured_weeks else self._quiz_deadline_schedule(quiz_count, start_date)
        manual_required = False
        schedule_warning = None
        if not configured_weeks:
            if not start_date or not end_date:
                manual_required = True
                schedule_warning = 'Thiếu ngày bắt đầu/kết thúc block hoặc lớp. Hãy cấu hình tuần học tại /semesters.'
            elif (end_date - start_date).days + 1 > 49:
                manual_required = True
                schedule_warning = 'Block dài hơn 7 tuần. Hãy cấu hình tuần học tại /semesters để chia deadline quiz theo lịch nghỉ/lễ.'
            elif start_date.weekday() != 0:
                manual_required = True
                schedule_warning = 'Ngày bắt đầu block/lớp không phải Thứ 2. Hãy cấu hình tuần học tại /semesters.'
        schedule_by_number: dict[int, dict[str, Any]] = {}
        for item in schedule_items:
            for number in item.get('quiz_numbers') or []:
                schedule_by_number[int(number)] = {
                    **item,
                    'deadline_mode': 'manual_required' if manual_required else ('semester_week_config' if configured_weeks else 'auto'),
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

    def _enrich_component_scores_for_class(
        self,
        items: list[dict[str, Any]],
        cls: AcademicClass | None,
        schedule_by_number: dict[int, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        normalized = list(items or [])
        schedule_by_number = schedule_by_number if schedule_by_number is not None else self._quiz_schedule_map_for_class(cls, normalized)
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
            configured_weeks = self._learning_week_schedule_from_block(block)
            schedule = self._quiz_deadline_schedule_from_weeks(quiz_count, configured_weeks) if configured_weeks else self._quiz_deadline_schedule(quiz_count, block_start)
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
        # v25.9.16.6.5: quiz deadlines may already be configured explicitly
        # in academic_quiz_deadline_overrides. Prefer those over inferred schedule
        # before the frontend builds Quiz columns, otherwise UI can show
        # "Cần chỉnh deadline tay" even though the class already has deadlines.
        if cls and results:
            course_id = next((snapshot.openedx_course_id for snapshot in snapshots if snapshot.openedx_course_id), None)
            overrides = TrainingPolicyService(self.db).deadline_overrides_for_class(cls.id, course_id)
            for item in results:
                numbers = self._quiz_numbers_from_component_item(item)
                if not numbers:
                    continue
                override = overrides.get(numbers[0])
                if not override:
                    continue
                if override.deadline_date:
                    item['deadline_date'] = override.deadline_date.isoformat()
                    item['deadline_mode'] = 'quiz_deadline_configured'
                    item['schedule_warning'] = None
                if override.start_date:
                    item['available_from'] = override.start_date.isoformat()
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
            'exam_not_eligible': 'exam_not_eligible', 'not_eligible': 'exam_not_eligible',
            'exam_insufficient_data': 'exam_insufficient_data', 'insufficient_data': 'exam_insufficient_data',
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


    def auto_map_subject_courses_for_filter(
        self,
        user: UserContext,
        *,
        term_id: str,
        branch: str | None = None,
        campus: str | None = None,
        search: str | None = None,
        learning_status: str | None = None,
        max_classes: int = 3000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Auto-map every safe subject in the current student-management filter.

        This method only creates safe subject-level Course CMS mappings and
        returns the classes that can now run the existing full CMS sync flow.
        The route enqueues class jobs so job de-duplication remains centralized.
        """
        term = self.db.get(AcademicTerm, term_id)
        if not term:
            raise HTTPException(status_code=404, detail='Không tìm thấy học kỳ AP')
        branch_value = (branch or term.branch or '').strip().lower() or None
        campus_value = campus.strip().lower() if campus and campus.strip() else None
        max_classes_value = max(1, min(5000, int(max_classes or 3000)))

        page = 1
        subjects: list[dict[str, Any]] = []
        while True:
            batch = self.list_teacher_subjects(
                user,
                term_id=term_id,
                branch=branch_value,
                campus=campus_value,
                search=search,
                learning_status=learning_status,
                page=page,
                page_size=200,
            )
            subjects.extend(batch.get('items') or [])
            if not batch.get('has_next'):
                break
            page += 1
            if page > 50:
                break

        visible_subject_ids = [str(item.get('id') or '') for item in subjects if str(item.get('id') or '')]
        mapped_subject_ids: set[str] = set(visible_subject_ids) if dry_run else set()
        subject_results: list[dict[str, Any]] = []
        already_mapped = 0
        auto_mapped = 0
        failed = 0
        for item in subjects:
            subject_id = str(item.get('id') or '')
            if not subject_id:
                continue
            if dry_run:
                subject_results.append({
                    'subject_id': subject_id,
                    'subject_code': item.get('subject_code'),
                    'status': 'scope_only',
                    'ok': True,
                    'openedx_course_id': item.get('openedx_course_id'),
                    'message': 'Môn nằm trong phạm vi được phân quyền.',
                })
                continue
            status_value = str(item.get('course_mapping_status') or '').lower()
            if status_value in {'mapped', 'already_mapped', 'auto_mapped'}:
                mapped_subject_ids.add(subject_id)
                already_mapped += 1
                subject_results.append({
                    'subject_id': subject_id,
                    'subject_code': item.get('subject_code'),
                    'status': 'already_mapped',
                    'ok': True,
                    'openedx_course_id': item.get('openedx_course_id'),
                    'message': 'Môn đã có Course CMS.',
                })
                continue
            try:
                result = self.auto_map_subject_course(user, term_id=term_id, subject_id=subject_id, branch=branch_value)
            except Exception as exc:  # keep bulk operation best-effort
                failed += 1
                subject_results.append({
                    'subject_id': subject_id,
                    'subject_code': item.get('subject_code'),
                    'status': 'failed',
                    'ok': False,
                    'message': str(exc),
                })
                continue
            ok = bool(result.get('ok'))
            if ok:
                mapped_subject_ids.add(subject_id)
                if result.get('status') == 'already_mapped':
                    already_mapped += 1
                else:
                    auto_mapped += 1
            else:
                failed += 1
            mapping = result.get('mapping') if isinstance(result.get('mapping'), dict) else None
            subject_results.append({
                'subject_id': subject_id,
                'subject_code': item.get('subject_code'),
                'status': result.get('status'),
                'ok': ok,
                'openedx_course_id': (mapping or {}).get('openedx_course_id') or item.get('openedx_course_id'),
                'message': result.get('message'),
            })

        class_ids: list[str] = []
        class_total = 0
        capped = False
        if mapped_subject_ids:
            decision = self.access_decision(user)
            class_query = self.db.query(AcademicClass).filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id == term_id,
                AcademicClass.subject_id.in_(list(mapped_subject_ids)),
            )
            if branch_value:
                class_query = class_query.filter(func.lower(AcademicClass.branch) == branch_value)
            if campus_value:
                class_query = class_query.filter(func.lower(AcademicClass.campus) == campus_value)
            class_query = self._apply_academic_access_filter(class_query, user, decision)
            class_total = class_query.count()
            capped = class_total > max_classes_value
            classes = class_query.order_by(AcademicClass.subject_id.asc(), AcademicClass.class_code.asc()).limit(max_classes_value).all()
            class_ids = [cls.id for cls in classes]

        return {
            'ok': True,
            'term_id': term_id,
            'branch': branch_value,
            'campus': campus_value,
            'subject_total': len(subjects),
            'subject_mapped': auto_mapped,
            'subject_already_mapped': already_mapped,
            'subject_failed': failed,
            'class_total': class_total,
            'class_ids': class_ids,
            'capped': capped,
            'subject_results': subject_results,
            'subject_ids': visible_subject_ids,
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
            query = query.filter(func.lower(AcademicClass.campus) == campus.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))
        query = query.group_by(AcademicSubject.id)
        ordered = query.order_by(AcademicSubject.subject_code.asc())

        # The subject screen is intentionally a compact subject list, but its KPI
        # cards must represent the whole current filter. The number of subjects in
        # one branch/campus/term is small enough to aggregate once here and avoids
        # the misleading "page only" totals that made the student/teacher pages
        # look inconsistent after a report rebuild.
        all_rows = ordered.all()
        base_total = len(all_rows)
        all_subject_ids = [row[0].id for row in all_rows]

        mapping_rows_all = []
        if all_subject_ids and term_id:
            mapping_query_all = self.db.query(AcademicCourseMapping).filter(
                AcademicCourseMapping.term_id == term_id,
                AcademicCourseMapping.subject_id.in_(all_subject_ids),
                AcademicCourseMapping.active.is_(True),
                AcademicCourseMapping.block_id.is_(None),
                AcademicCourseMapping.campus.is_(None),
            )
            if branch:
                mapping_query_all = mapping_query_all.filter(AcademicCourseMapping.branch == branch.strip().lower())
            mapping_rows_all = mapping_query_all.all()
        mapping_by_subject_all = {item.subject_id: item for item in mapping_rows_all}

        sync_summary_all = self._student_sync_summary_for_subjects(user, term_id, all_subject_ids, branch=branch, campus=campus, decision=decision)
        learning_all = self._learning_summary_by_subject_ids(
            all_subject_ids,
            term_id=term_id,
            branch=branch,
            campus=campus,
            course_by_subject={subject_id: mapping_by_subject_all.get(subject_id).openedx_course_id if mapping_by_subject_all.get(subject_id) else None for subject_id in all_subject_ids},
            decision=decision,
            user=user,
        )

        def build_entry(row: Any) -> dict[str, Any]:
            subject = row[0]
            mapping = mapping_by_subject_all.get(subject.id)
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
            counts = sync_summary_all.get(subject.id, {})
            entry = {
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
            }
            entry.update(learning_all.get(subject.id, {}))
            return entry

        all_items = [build_entry(row) for row in all_rows]
        if needs_status_filter:
            filtered_items = [entry for entry in all_items if self._entry_matches_learning_list_filter(entry, status_filter)]
        else:
            filtered_items = all_items
        total = len(filtered_items) if needs_status_filter else base_total
        items = filtered_items[(page - 1) * page_size:page * page_size]
        total_pages = math.ceil(total / page_size) if total else 0

        summary_source = filtered_items if needs_status_filter else all_items
        summary = {
            'subject_count': int(total),
            'class_count': int(sum(item.get('class_count') or 0 for item in summary_source)),
            'student_count': int(sum(item.get('student_count') or 0 for item in summary_source)),
            'teacher_count': int(sum(item.get('teacher_count') or 0 for item in summary_source)),
            'cms_synced_count': int(sum(item.get('cms_synced_count') or 0 for item in summary_source)),
            'cms_unsynced_count': int(sum(item.get('cms_unsynced_count') or 0 for item in summary_source)),
            'course_mapped_count': int(sum(1 for item in summary_source if str(item.get('course_mapping_status') or '').lower() in {'mapped', 'already_mapped', 'auto_mapped'})),
            'course_missing_count': int(sum(1 for item in summary_source if str(item.get('course_mapping_status') or '').lower() in {'not_found', 'multiple_candidates'})),
            'learning_enrolled_count': int(sum(item.get('learning_enrolled_count') or 0 for item in summary_source)),
            'learning_active_count': int(sum(item.get('learning_active_count') or 0 for item in summary_source)),
            'learning_synced_count': int(sum(item.get('learning_synced_count') or 0 for item in summary_source)),
            'alert_subject_count': int(sum(1 for item in summary_source if item.get('learning_alerts'))),
            'scope_label': 'Toàn bộ bộ lọc',
        }
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': page < total_pages, 'summary': summary}

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
        quiz_schedule_by_number: dict[int, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        cls = cls or self.db.get(AcademicClass, class_id)
        block = block if block is not None else (self._block_for_class(cls) if cls else None)
        components = self._enrich_component_scores_for_class(self._component_scores_from_snapshot(learning), cls, quiz_schedule_by_number)
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
            'learning_progress_source': self._snapshot_progress_source(learning),
            'learning_grade_percent': self._snapshot_grade_percent(learning),
            'learning_passed': learning.passed if learning else None,
            'learning_completed_blocks': learning.completed_blocks if learning else None,
            'learning_total_blocks': learning.total_blocks if learning else None,
            'learning_last_activity_at': learning.last_activity_at if learning else None,
            'learning_last_synced_at': (learning.learning_synced_at or learning.last_synced_at) if learning else None,
            'learning_enrollment_synced_at': learning.enrollment_synced_at if learning else None,
            'learning_status': self._learning_status_for_snapshot(learning, mapping),
            # Keep the hot class-detail API lean. Full diagnostic text is no longer
            # returned per student because the UI does not display it and it adds
            # measurable JSON/CPU overhead on large classes.
            'learning_diagnostics': None,
            'learning_sync_note': None,
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
        return AcademicRosterWorkflowService(self.db, parent=self).list_class_students(
            user,
            class_id,
            search=search,
            learning_status=learning_status,
            page=page,
            page_size=page_size,
        )

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
    ) -> tuple[dict[str, dict[str, int]], dict[tuple[str, str], AcademicStudentLearningSnapshot], dict[tuple[str, str], str]]:
        if not class_ids:
            return {}, {}, {}
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
        status_by_class_student: dict[tuple[str, str], str] = {}
        for class_id, student_id, mapping in rows:
            status_name = self._learning_status_for_snapshot(snapshot_by_class_student.get((class_id, student_id)), mapping)
            status_by_class_student[(class_id, student_id)] = status_name
            bucket = counts_by_class.setdefault(class_id, {})
            bucket[status_name] = bucket.get(status_name, 0) + 1
        return counts_by_class, snapshot_by_class_student, status_by_class_student

    @staticmethod
    def _campus_filter_value(value: Any) -> str:
        return str(value or '').strip().lower()

    @staticmethod
    def _risk_status_keys() -> set[str]:
        # Only buckets that represent an actionable learning/CMS issue.
        # "exam_insufficient_data" is intentionally excluded: it is a data-quality state,
        # not a per-learner risk. Counting it as a warning turned missing snapshots into
        # tens of thousands of false "Cần theo dõi" records on training-management.
        return {
            'cms_not_synced',
            'not_synced',
            'not_enrolled',
            'sync_error',
            'no_activity',
            'low_progress',
            'low_grade',
            'deadline_late',
            'exam_not_eligible',
        }

    @classmethod
    def _bounded_risk_count_from_status_counts(cls, status_counts: dict[str, Any], total_students: int) -> int:
        """Return a safe non-overlapping warning count for aggregate rows.

        The status buckets are not mutually exclusive after deadline/exam buckets are
        merged into learning status counts. Summing them can exceed the number of
        students (for example 52k students -> 105k warnings). For aggregate cards where
        we do not have row-level ids, cap the warning count and prefer the largest
        actionable bucket as a conservative approximation.
        """
        total = max(0, int(total_students or 0))
        if total <= 0:
            return 0
        actionable_values = [max(0, int(status_counts.get(key, 0) or 0)) for key in cls._risk_status_keys()]
        return min(total, max(actionable_values) if actionable_values else 0)

    def _training_teacher_report_workflow(self):
        return AcademicTeacherReportWorkflowService(self.db, self)

    @staticmethod
    def _teacher_report_scope_key(term_id: str | None, branch: str | None, campus: str | None) -> str:
        return AcademicTeacherReportWorkflowService._teacher_report_scope_key(term_id, branch, campus)

    @staticmethod
    def _teacher_report_search_match(item: dict[str, Any], search: str | None) -> bool:
        return AcademicTeacherReportWorkflowService._teacher_report_search_match(item, search)

    def _teacher_report_item_matches_filter(self, item: dict[str, Any], status_filter: str | None) -> bool:
        return self._training_teacher_report_workflow()._teacher_report_item_matches_filter(item, status_filter)

    @staticmethod
    def _teacher_report_item_allowed_for_decision(item: dict[str, Any], decision: AccessDecision) -> bool:
        return AcademicTeacherReportWorkflowService._teacher_report_item_allowed_for_decision(item, decision)

    @staticmethod
    def _teacher_report_public_item(item: dict[str, Any], *, include_classes: bool) -> dict[str, Any]:
        return AcademicTeacherReportWorkflowService._teacher_report_public_item(item, include_classes=include_classes)

    def _teacher_report_summary_from_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._training_teacher_report_workflow()._teacher_report_summary_from_items(items)

    def _training_teacher_report_lite_fast(self, user: UserContext, *, term_id: str | None, branch: str | None, campus: str | None, search: str | None, learning_status: str | None, teacher_id: str | None, page: int, page_size: int, decision: AccessDecision) -> dict[str, Any] | None:
        return self._training_teacher_report_workflow()._training_teacher_report_lite_fast(user, term_id=term_id, branch=branch, campus=campus, search=search, learning_status=learning_status, teacher_id=teacher_id, page=page, page_size=page_size, decision=decision)

    def _training_teacher_report_from_cache(self, *, term_id: str | None, branch: str | None, campus: str | None, search: str | None, learning_status: str | None, teacher_id: str | None, page: int, page_size: int, decision: AccessDecision, include_classes: bool) -> dict[str, Any] | None:
        return self._training_teacher_report_workflow()._training_teacher_report_from_cache(term_id=term_id, branch=branch, campus=campus, search=search, learning_status=learning_status, teacher_id=teacher_id, page=page, page_size=page_size, decision=decision, include_classes=include_classes)

    def rebuild_training_teacher_report_cache(self, user: UserContext, *, term_id: str, branch: str | None = None, campus: str | None = None, source_sync_run_id: str | None = None) -> dict[str, Any]:
        return self._training_teacher_report_workflow().rebuild_training_teacher_report_cache(user, term_id=term_id, branch=branch, campus=campus, source_sync_run_id=source_sync_run_id)

    def training_teacher_report(self, user: UserContext, *, term_id: str | None = None, branch: str | None = None, campus: str | None = None, search: str | None = None, learning_status: str | None = None, teacher_id: str | None = None, page: int = 1, page_size: int = 50, include_all: bool = False, include_classes: bool = False, include_students: bool = False, use_cache: bool = True) -> dict[str, Any]:
        return self._training_teacher_report_workflow().training_teacher_report(user, term_id=term_id, branch=branch, campus=campus, search=search, learning_status=learning_status, teacher_id=teacher_id, page=page, page_size=page_size, include_all=include_all, include_classes=include_classes, include_students=include_students, use_cache=use_cache)

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
        mapping.openedx_course_id = str((validation.get('parsed_course') or {}).get('raw') or '').strip()
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
        mapping.openedx_course_id = str((validation.get('parsed_course') or {}).get('raw') or '').strip()
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
        # v25.9.16.5.98: course mapping changes make old learning snapshots and
        # teacher report cache stale. Remove class snapshots so the UI does not
        # show progress/grades from a previous Course CMS mapping.
        self.db.query(AcademicStudentLearningSnapshot).filter(AcademicStudentLearningSnapshot.class_id == class_id).delete(synchronize_session=False)
        cache_invalidated = self._invalidate_teacher_report_cache_for_class(class_id, reason='course_mapping_changed')
        self.db.commit()
        self.db.refresh(mapping)
        result = self._class_course_mapping_item(mapping)
        result['cache_invalidated'] = {'teacher_report_rows': cache_invalidated, 'reason': 'course_mapping_changed'}
        result['learning_snapshots_cleared'] = True
        return result

    def deactivate_class_course_mapping(self, user: UserContext, class_id: str) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        mapping = self.db.query(AcademicClassCourseMapping).filter(AcademicClassCourseMapping.class_id == class_id, AcademicClassCourseMapping.active.is_(True)).first()
        if not mapping:
            raise HTTPException(status_code=404, detail='Lớp này chưa có mapping course riêng')
        mapping.active = False
        mapping.updated_by = user.user_id
        mapping.updated_at = datetime.utcnow()
        self.db.add(mapping)
        self.db.query(AcademicStudentLearningSnapshot).filter(AcademicStudentLearningSnapshot.class_id == class_id).delete(synchronize_session=False)
        cache_invalidated = self._invalidate_teacher_report_cache_for_class(class_id, reason='course_mapping_deactivated')
        self.db.commit()
        result = self._class_course_mapping_item(mapping)
        result['cache_invalidated'] = {'teacher_report_rows': cache_invalidated, 'reason': 'course_mapping_deactivated'}
        result['learning_snapshots_cleared'] = True
        return result

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


    def _student_cms_username(self, student: AcademicStudent) -> str:
        return self._academic_sync_enrollment_workflow()._student_cms_username(student)

    def _student_cms_email(self, student: AcademicStudent) -> str | None:
        return self._academic_sync_enrollment_workflow()._student_cms_email(student)

    def _student_cms_payload(self, student: AcademicStudent, *, create_missing: bool, openedx_user_id: str | None = None) -> dict[str, Any]:
        return self._academic_sync_enrollment_workflow()._student_cms_payload(student, create_missing=create_missing, openedx_user_id=openedx_user_id)

    def _upsert_teacher_cms_metadata(self, teacher: AcademicTeacher, result: dict[str, Any] | None) -> str:
        return self._academic_sync_enrollment_workflow()._upsert_teacher_cms_metadata(teacher, result)

    def resolve_class_openedx_users(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, auto_enroll: bool = True) -> dict[str, Any]:
        return self._academic_sync_enrollment_workflow().resolve_class_openedx_users(user, class_id, force=force, limit=limit, auto_enroll=auto_enroll)

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
        return to_vn_naive_datetime(value)

    def _learning_summary_for_class_course(self, class_id: str, course_id: str | None) -> dict[str, Any]:
        total = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == class_id).scalar() or 0
        empty_diagnostics = {
            'official_progress': 0,
            'student_module_progress': 0,
            'with_progress_percent': 0,
            'with_grade_percent': 0,
            'with_component_grades': 0,
            'progress_na': int(total),
            'grade_na': int(total),
            'component_na': int(total),
        }
        if not course_id:
            return {
                'class_id': class_id,
                'openedx_course_id': None,
                'total': int(total),
                'counts': {'not_synced': int(total)},
                'active_count': 0,
                'avg_progress_percent': None,
                'avg_grade_percent': None,
                'last_synced_at': None,
                'component_summaries': [],
                'status_counts': {'not_synced': int(total)},
                'alert_counts': {'not_synced': int(total)},
                'diagnostic_counts': empty_diagnostics,
                'source_counts': {},
                'diagnostic_note': 'Lớp chưa map Course CMS nên chưa thể đọc Course Home Progress/grade.',
            }
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
        diagnostic_counts = {
            'official_progress': 0,
            'student_module_progress': 0,
            'with_progress_percent': 0,
            'with_grade_percent': 0,
            'with_component_grades': 0,
            'progress_na': 0,
            'grade_na': 0,
            'component_na': 0,
        }
        source_counts: dict[str, int] = {}
        for student_id, mapping in mapping_rows:
            snapshot = snapshot_by_student.get(student_id)
            status_name = self._learning_status_for_snapshot(snapshot, mapping)
            status_counts[status_name] = status_counts.get(status_name, 0) + 1
            if status_name in alert_counts:
                alert_counts[status_name] += 1
            progress_percent = self._snapshot_progress_percent(snapshot)
            grade_percent = self._snapshot_grade_percent(snapshot)
            components = self._component_scores_from_snapshot(snapshot)
            source = self._snapshot_progress_source(snapshot) or ''
            source_l = source.lower()
            if progress_percent is not None:
                diagnostic_counts['with_progress_percent'] += 1
            else:
                diagnostic_counts['progress_na'] += 1
            if grade_percent is not None:
                diagnostic_counts['with_grade_percent'] += 1
            else:
                diagnostic_counts['grade_na'] += 1
            if components:
                diagnostic_counts['with_component_grades'] += 1
            else:
                diagnostic_counts['component_na'] += 1
            if 'studentmodule' in source_l:
                diagnostic_counts['student_module_progress'] += 1
            if 'coursehome' in source_l or 'completion_summary' in source_l:
                diagnostic_counts['official_progress'] += 1
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
        diagnostic_note = None
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
            'diagnostic_counts': diagnostic_counts,
            'source_counts': source_counts,
            'diagnostic_note': diagnostic_note,
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
        previous_progress_percent = snapshot.progress_percent
        previous_grade_percent = snapshot.grade_percent
        previous_completed_blocks = snapshot.completed_blocks
        previous_total_blocks = snapshot.total_blocks
        previous_raw_json = snapshot.raw_json if isinstance(snapshot.raw_json, dict) else {}
        enrollment = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
        progress = result.get('progress') if isinstance(result.get('progress'), dict) else {}
        grade = result.get('grade') if isinstance(result.get('grade'), dict) else {}
        completion_summary = progress.get('completion_summary') if isinstance(progress.get('completion_summary'), dict) else None
        if completion_summary is None and isinstance((progress.get('payload') if isinstance(progress, dict) else None), dict):
            completion_summary = progress.get('payload', {}).get('completion_summary') if isinstance(progress.get('payload', {}).get('completion_summary'), dict) else None
        snapshot.openedx_username = str(result.get('openedx_username') or result.get('username') or student.username or '').strip() or None
        snapshot.openedx_user_id = str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None
        snapshot.enrollment_status = str(
            result.get('enrollment_status')
            or enrollment.get('status')
            or ('enrolled' if enrollment.get('is_enrolled') is True else ('not_enrolled' if enrollment.get('is_enrolled') is False else 'unknown'))
        )[:50]
        snapshot.enrollment_mode = str(result.get('enrollment_mode') or enrollment.get('mode') or '').strip()[:50] or None
        accepted_progress_payload = self._has_accepted_progress_payload(result)
        if accepted_progress_payload:
            snapshot.progress_percent = self._float_or_none(result.get('progress_percent', progress.get('percent')))
            if snapshot.progress_percent is None:
                snapshot.progress_percent = self._progress_percent_from_payload(result)
        else:
            # v25.9.16.5.97: never overwrite a previously-good progress value
            # with a connector payload that lacks the locked progress contract.
            snapshot.progress_percent = previous_progress_percent
        incoming_grade_percent = self._float_or_none(result.get('grade_percent', grade.get('percent')))
        if incoming_grade_percent is None:
            incoming_grade_percent = self._grade_percent_from_payload(result)
        snapshot.grade_percent = incoming_grade_percent if incoming_grade_percent is not None else previous_grade_percent
        if 'passed' in result:
            snapshot.passed = _boolish(result.get('passed'))
        elif 'passed' in grade:
            snapshot.passed = _boolish(grade.get('passed'))
        incoming_completed_blocks = self._int_or_none(
            result.get('completed_blocks')
            or progress.get('completed_blocks')
            or (completion_summary or {}).get('complete_count')
            or (completion_summary or {}).get('completed_count')
        )
        incoming_total_blocks = self._int_or_none(
            result.get('total_blocks')
            or progress.get('total_blocks')
            or (
                (self._int_or_none((completion_summary or {}).get('complete_count')) or 0)
                + (self._int_or_none((completion_summary or {}).get('incomplete_count')) or 0)
                if completion_summary else None
            )
        )
        snapshot.completed_blocks = incoming_completed_blocks if incoming_completed_blocks is not None else previous_completed_blocks
        snapshot.total_blocks = incoming_total_blocks if incoming_total_blocks is not None else previous_total_blocks
        snapshot.last_activity_at = self._dt_or_none(result.get('last_activity_at') or progress.get('last_activity_at'))
        diagnostic_payload = {
            'official_progress': self._is_official_progress_payload(result),
            'student_module_progress': self._is_student_module_progress_payload(result),
            'progress_source': result.get('progress_source') or progress.get('source'),
            'completed_blocks': snapshot.completed_blocks,
            'total_blocks': snapshot.total_blocks,
            'has_progress_percent': snapshot.progress_percent is not None,
            'has_grade_percent': snapshot.grade_percent is not None,
            'has_component_grades': bool(self._component_scores_from_payload(result)),
        }
        snapshot.raw_json = {
            'source': source,
            'payload': _json_safe_value(result),
            'learning_diagnostics': _json_safe_value(diagnostic_payload),
            'previous_preserved': bool((not accepted_progress_payload and previous_progress_percent is not None) or (incoming_grade_percent is None and previous_grade_percent is not None)),
            'previous_source': previous_raw_json.get('source'),
        }
        snapshot.learning_synced_at = now
        snapshot.last_synced_at = now
        snapshot.updated_at = now
        self.db.add(snapshot)
        return snapshot


    def _upsert_enrollment_snapshot(self, *, class_id: str, student: AcademicStudent, course_id: str, result: dict[str, Any], source: str) -> AcademicStudentLearningSnapshot:
        return self._academic_sync_enrollment_workflow()._upsert_enrollment_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source=source)

    def sync_class_course_enrollment(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, mode: str | None = None) -> dict[str, Any]:
        return self._academic_sync_enrollment_workflow().sync_class_course_enrollment(user, class_id, force=force, limit=limit, mode=mode)

    def sync_class_learning_insight(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        return self._academic_sync_enrollment_workflow().sync_class_learning_insight(user, class_id, force=force, limit=limit)


    def _try_auto_map_course_for_class(self, user: UserContext, cls: AcademicClass) -> dict[str, Any]:
        return self._academic_sync_enrollment_workflow()._try_auto_map_course_for_class(user, cls)

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
        return self._academic_sync_enrollment_workflow().sync_class_full_cms_flow(user, class_id, force=force, limit=limit, mode=mode, auto_map_course=auto_map_course, sync_learning=sync_learning)


    def _identity_reconciliation_status(self, student: AcademicStudent, mapping: OpenEdXUserMapping | None, *, duplicate_code_count: int = 0, duplicate_canonical_mapping_count: int = 0) -> dict[str, Any]:
            return self._academic_identity_workflow()._identity_reconciliation_status(student, mapping, duplicate_code_count=duplicate_code_count, duplicate_canonical_mapping_count=duplicate_canonical_mapping_count)

    def identity_reconciliation_for_class(
            self,
            user: UserContext,
            class_id: str,
            *,
            status_filter: str | None = None,
            page: int = 1,
            page_size: int = 200,
        ) -> dict[str, Any]:
            return self._academic_identity_workflow().identity_reconciliation_for_class(user, class_id, status_filter=status_filter, page=page, page_size=page_size)


    def cleanup_identity_reconciliation_for_class(self, user: UserContext, class_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            return self._academic_identity_workflow().cleanup_identity_reconciliation_for_class(user, class_id, payload=payload)

    def _identity_reconciliation_next_actions(self, counts: dict[str, int]) -> list[str]:
            return self._academic_identity_workflow()._identity_reconciliation_next_actions(counts)


    def rollnumber_identity_migration_report(
            self,
            user: UserContext,
            *,
            class_id: str | None = None,
            term_id: str | None = None,
            campus: str | None = None,
            branch: str | None = None,
            subject_id: str | None = None,
            status_filter: str | None = None,
            page: int = 1,
            page_size: int = 200,
        ) -> dict[str, Any]:
            return self._academic_identity_workflow().rollnumber_identity_migration_report(user, class_id=class_id, term_id=term_id, campus=campus, branch=branch, subject_id=subject_id, status_filter=status_filter, page=page, page_size=page_size)


    def import_openedx_user_mappings(self, records: list[dict[str, Any]], *, requested_by: str | None = None) -> dict[str, Any]:
            return self._academic_identity_workflow().import_openedx_user_mappings(records, requested_by=requested_by)

