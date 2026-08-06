from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, case, func, inspect, literal, or_, text
from sqlalchemy.orm import Session

from app.core.json_safe import json_safe_value
from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTerm,
    UdemySubjectPlan,
    UdemySubjectPlanMilestone,
    UdemyStudentProgress,
)
from app.services.ap_academic_sync import APAcademicClient, AcademicImportService, SyncCounters


class AcademicSubjectDeliveryService:
    """Term/block learning-platform catalog for CMS and Udemy subjects."""

    VALID_PLATFORMS = {None, 'cms', 'udemy'}
    CMS_JOB_TYPES = {'cms_sync_check', 'cms_enrollment_sync', 'learning_sync', 'full_cms_sync'}

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_branch(value: str | None) -> str:
        return (value or 'poly').strip().lower() or 'poly'

    @classmethod
    def normalize_platform(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in {'', 'none', 'null', 'unassigned'}:
            return None
        if normalized not in {'cms', 'udemy'}:
            raise HTTPException(status_code=422, detail='Nền tảng chỉ nhận cms, udemy hoặc chưa chọn.')
        return normalized

    @staticmethod
    def _subject_code_from_item(item: dict[str, Any]) -> str:
        return str(item.get('psubject_code') or item.get('subject_code') or item.get('id') or '').strip().upper()

    def _get_scope(self, *, term_id: str, block_id: str, branch: str | None) -> tuple[AcademicTerm, AcademicBlock, str]:
        term = self.db.get(AcademicTerm, term_id)
        block = self.db.get(AcademicBlock, block_id)
        branch_value = self.normalize_branch(branch or (term.branch if term else None))
        if not term:
            raise HTTPException(status_code=404, detail='Không tìm thấy học kỳ.')
        if not block or block.term_id != term.id:
            raise HTTPException(status_code=422, detail='Block không thuộc học kỳ đã chọn.')
        return term, block, branch_value

    def list_deliveries(
        self,
        *,
        term_id: str | None = None,
        block_id: str | None = None,
        branch: str | None = None,
        learning_platform: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        platform_filter = self.normalize_platform(learning_platform) if learning_platform not in {None, '', 'all'} else 'all'
        branch_value = self.normalize_branch(branch) if branch else None

        class_counts = (
            self.db.query(
                AcademicClass.subject_id.label('subject_id'),
                AcademicClass.term_id.label('term_id'),
                AcademicClass.block_id.label('block_id'),
                func.lower(func.coalesce(AcademicClass.branch, '')).label('branch_key'),
                func.count(AcademicClass.id).label('class_count'),
                func.count(func.distinct(AcademicClass.campus)).label('campus_count'),
            )
            .filter(AcademicClass.active.is_(True))
            .group_by(AcademicClass.subject_id, AcademicClass.term_id, AcademicClass.block_id, func.lower(func.coalesce(AcademicClass.branch, '')))
            .subquery()
        )

        active_plan = (
            self.db.query(
                UdemySubjectPlan.id.label('plan_id'),
                UdemySubjectPlan.subject_delivery_id.label('subject_delivery_id'),
                UdemySubjectPlan.version.label('plan_version'),
                UdemySubjectPlan.item_count.label('item_count'),
                UdemySubjectPlan.imported_at.label('plan_imported_at'),
                UdemySubjectPlan.updated_at.label('plan_updated_at'),
            )
            .filter(UdemySubjectPlan.active.is_(True))
            .subquery()
        )
        milestone_counts = (
            self.db.query(
                UdemySubjectPlanMilestone.plan_id.label('plan_id'),
                func.count(UdemySubjectPlanMilestone.id).label('milestone_count'),
            )
            .group_by(UdemySubjectPlanMilestone.plan_id)
            .subquery()
        )
        progress_table_available = bool(inspect(self.db.get_bind()).has_table('udemy_student_progress'))
        progress_stats = None
        if progress_table_available:
            progress_stats = (
                self.db.query(
                    UdemyStudentProgress.subject_delivery_id.label('subject_delivery_id'),
                    func.count(UdemyStudentProgress.id).label('student_count'),
                    func.sum(case((UdemyStudentProgress.is_late.is_(True), 1), else_=0)).label('late_count'),
                    func.sum(case((UdemyStudentProgress.match_status != 'matched_roster', 1), else_=0)).label('unmatched_count'),
                    func.max(UdemyStudentProgress.last_imported_at).label('last_imported_at'),
                )
                .group_by(UdemyStudentProgress.subject_delivery_id)
                .subquery()
            )
        progress_student_expr = func.coalesce(progress_stats.c.student_count, 0) if progress_stats is not None else literal(0)
        progress_late_expr = func.coalesce(progress_stats.c.late_count, 0) if progress_stats is not None else literal(0)
        progress_unmatched_expr = func.coalesce(progress_stats.c.unmatched_count, 0) if progress_stats is not None else literal(0)
        progress_last_expr = progress_stats.c.last_imported_at if progress_stats is not None else literal(None)

        query = (
            self.db.query(
                AcademicSubjectDelivery,
                AcademicSubject,
                AcademicTerm,
                AcademicBlock,
                func.coalesce(class_counts.c.class_count, 0).label('class_count'),
                func.coalesce(class_counts.c.campus_count, 0).label('campus_count'),
                active_plan.c.plan_id,
                active_plan.c.plan_version,
                active_plan.c.item_count,
                func.coalesce(milestone_counts.c.milestone_count, 0).label('milestone_count'),
                active_plan.c.plan_imported_at,
                active_plan.c.plan_updated_at,
                progress_student_expr.label('udemy_progress_student_count'),
                progress_late_expr.label('udemy_progress_late_count'),
                progress_unmatched_expr.label('udemy_progress_unmatched_count'),
                progress_last_expr.label('last_udemy_import_at'),
            )
            .join(AcademicSubject, AcademicSubject.id == AcademicSubjectDelivery.subject_id)
            .join(AcademicTerm, AcademicTerm.id == AcademicSubjectDelivery.term_id)
            .join(AcademicBlock, AcademicBlock.id == AcademicSubjectDelivery.block_id)
            .outerjoin(
                class_counts,
                and_(
                    class_counts.c.subject_id == AcademicSubjectDelivery.subject_id,
                    class_counts.c.term_id == AcademicSubjectDelivery.term_id,
                    class_counts.c.block_id == AcademicSubjectDelivery.block_id,
                    class_counts.c.branch_key == func.lower(AcademicSubjectDelivery.branch),
                ),
            )
            .outerjoin(active_plan, active_plan.c.subject_delivery_id == AcademicSubjectDelivery.id)
            .outerjoin(milestone_counts, milestone_counts.c.plan_id == active_plan.c.plan_id)
        )
        if progress_stats is not None:
            query = query.outerjoin(progress_stats, progress_stats.c.subject_delivery_id == AcademicSubjectDelivery.id)
        query = query.filter(AcademicSubjectDelivery.active.is_(True), AcademicSubject.active.is_(True))
        if term_id:
            query = query.filter(AcademicSubjectDelivery.term_id == term_id)
        if block_id:
            query = query.filter(AcademicSubjectDelivery.block_id == block_id)
        if branch_value:
            query = query.filter(func.lower(AcademicSubjectDelivery.branch) == branch_value)
        if platform_filter != 'all':
            if platform_filter is None:
                query = query.filter(AcademicSubjectDelivery.learning_platform.is_(None))
            else:
                query = query.filter(AcademicSubjectDelivery.learning_platform == platform_filter)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))

        rows = query.order_by(AcademicSubject.subject_code.asc(), AcademicSubject.subject_name.asc()).all()
        total = len(rows)
        page_value = max(1, int(page or 1))
        page_size_value = max(1, min(200, int(page_size or 50)))
        total_pages = math.ceil(total / page_size_value) if total else 0
        selected_rows = rows[(page_value - 1) * page_size_value:page_value * page_size_value]

        items: list[dict[str, Any]] = []
        for delivery, subject, term, block, class_count, campus_count, plan_id, plan_version, item_count, milestone_count, plan_imported_at, plan_updated_at, progress_student_count, progress_late_count, progress_unmatched_count, last_udemy_import_at in selected_rows:
            items.append({
                'id': delivery.id,
                'subject_id': subject.id,
                'ap_subject_id': subject.ap_subject_id,
                'subject_code': subject.subject_code,
                'subject_name': subject.subject_name,
                'subject_name_en': subject.subject_name_en,
                'skill_code': subject.skill_code,
                'term_id': term.id,
                'term_name': term.term_name,
                'block_id': block.id,
                'block_name': block.block_name,
                'branch': delivery.branch,
                'learning_platform': delivery.learning_platform,
                'active': delivery.active,
                'configuration_source': delivery.configuration_source,
                'configured_by': delivery.configured_by,
                'configured_at': delivery.configured_at,
                'catalog_refreshed_at': delivery.catalog_refreshed_at,
                'class_count': int(class_count or 0),
                'campus_count': int(campus_count or 0),
                'has_udemy_plan': bool(plan_id),
                'udemy_plan_id': plan_id,
                'udemy_plan_version': int(plan_version) if plan_version is not None else None,
                'udemy_item_count': int(item_count) if item_count is not None else None,
                'udemy_milestone_count': int(milestone_count or 0),
                'udemy_plan_updated_at': plan_updated_at or plan_imported_at,
                'last_udemy_import_at': last_udemy_import_at,
                'udemy_progress_student_count': int(progress_student_count or 0),
                'udemy_progress_late_count': int(progress_late_count or 0),
                'udemy_progress_unmatched_count': int(progress_unmatched_count or 0),
                'metadata_json': delivery.metadata_json if isinstance(delivery.metadata_json, dict) else {},
                'created_at': delivery.created_at,
                'updated_at': delivery.updated_at,
            })

        all_deliveries = [row[0] for row in rows]
        summary = {
            'total': total,
            'cms_count': sum(1 for item in all_deliveries if item.learning_platform == 'cms'),
            'udemy_count': sum(1 for item in all_deliveries if item.learning_platform == 'udemy'),
            'unassigned_count': sum(1 for item in all_deliveries if item.learning_platform is None),
            'class_count': sum(int(row[4] or 0) for row in rows),
            'scope_label': 'Toàn bộ bộ lọc',
        }
        return {
            'items': items,
            'total': total,
            'page': page_value,
            'page_size': page_size_value,
            'total_pages': total_pages,
            'has_next': page_value < total_pages,
            'summary': summary,
        }

    def set_platform(self, delivery_id: str, learning_platform: Any, *, actor: str | None, source: str = 'manual') -> AcademicSubjectDelivery:
        delivery = self.db.get(AcademicSubjectDelivery, delivery_id)
        if not delivery or not delivery.active:
            raise HTTPException(status_code=404, detail='Không tìm thấy môn trong phạm vi học kỳ/block.')
        next_platform = self.normalize_platform(learning_platform)
        previous_platform = delivery.learning_platform
        if previous_platform == next_platform:
            return delivery

        now = datetime.utcnow()
        metadata = dict(delivery.metadata_json or {}) if isinstance(delivery.metadata_json, dict) else {}
        history = list(metadata.get('platform_history') or [])
        history.append({
            'from': previous_platform,
            'to': next_platform,
            'source': source,
            'actor': actor,
            'changed_at': now.isoformat(),
        })
        metadata['platform_history'] = history[-100:]
        metadata['platform_policy_version'] = 'udemy-subject-management/batch31'
        delivery.learning_platform = next_platform
        delivery.configuration_source = source
        delivery.configured_by = actor
        delivery.configured_at = now
        delivery.updated_at = now
        delivery.metadata_json = json_safe_value(metadata)
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def bulk_set_platform(self, delivery_ids: list[str], learning_platform: Any, *, actor: str | None) -> list[AcademicSubjectDelivery]:
        unique_ids = list(dict.fromkeys(str(item).strip() for item in delivery_ids if str(item).strip()))
        if not unique_ids:
            raise HTTPException(status_code=422, detail='Chưa chọn môn cần cập nhật.')
        if len(unique_ids) > 2000:
            raise HTTPException(status_code=422, detail='Mỗi lần chỉ cập nhật tối đa 2.000 môn.')
        platform = self.normalize_platform(learning_platform)
        rows = self.db.query(AcademicSubjectDelivery).filter(AcademicSubjectDelivery.id.in_(unique_ids), AcademicSubjectDelivery.active.is_(True)).all()
        if len(rows) != len(unique_ids):
            found = {row.id for row in rows}
            missing = [item for item in unique_ids if item not in found]
            raise HTTPException(status_code=404, detail=f'Không tìm thấy {len(missing)} môn đã chọn. Hãy làm mới danh sách.')
        now = datetime.utcnow()
        for delivery in rows:
            previous_platform = delivery.learning_platform
            if previous_platform == platform:
                continue
            metadata = dict(delivery.metadata_json or {}) if isinstance(delivery.metadata_json, dict) else {}
            history = list(metadata.get('platform_history') or [])
            history.append({'from': previous_platform, 'to': platform, 'source': 'bulk_manual', 'actor': actor, 'changed_at': now.isoformat()})
            metadata['platform_history'] = history[-100:]
            metadata['platform_policy_version'] = 'udemy-subject-management/batch31'
            delivery.learning_platform = platform
            delivery.configuration_source = 'bulk_manual'
            delivery.configured_by = actor
            delivery.configured_at = now
            delivery.updated_at = now
            delivery.metadata_json = json_safe_value(metadata)
            self.db.add(delivery)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def refresh_catalog(self, *, term_id: str, block_id: str | None, branch: str | None, actor: str | None = None) -> dict[str, Any]:
        term = self.db.get(AcademicTerm, term_id)
        if not term:
            raise HTTPException(status_code=404, detail='Không tìm thấy học kỳ.')
        branch_value = self.normalize_branch(branch or term.branch)
        lock_key = f'academic-subject-catalog:{term_id}:{block_id or "all"}:{branch_value}'

        def acquire_scope_lock() -> None:
            try:
                bind = self.db.get_bind()
                if bind is not None and bind.dialect.name == 'postgresql':
                    self.db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': lock_key})
            except Exception:
                # The unique scope constraint remains the final safety net; SQLite
                # tests and restricted database users may not expose advisory locks.
                pass

        acquire_scope_lock()
        if block_id:
            block = self.db.get(AcademicBlock, block_id)
            if not block or block.term_id != term.id:
                raise HTTPException(status_code=422, detail='Block không thuộc học kỳ đã chọn.')
            blocks = [block]
        else:
            blocks = (
                self.db.query(AcademicBlock)
                .filter(AcademicBlock.term_id == term.id, AcademicBlock.active.is_(True))
                .order_by(AcademicBlock.sort_order.asc(), AcademicBlock.block_name.asc())
                .all()
            )
        if not blocks:
            raise HTTPException(status_code=422, detail='Học kỳ chưa có Block đang hoạt động.')

        client = APAcademicClient()
        raw_subjects = client.get_subjects(branch=branch_value, term_name=term.term_name, campus=None)
        counters = SyncCounters()
        AcademicImportService(self.db).import_subject_catalog(raw_subjects, branch=branch_value, counters=counters)
        # import_subject_catalog commits its own transaction. Reacquire the scope
        # lock before delivery upsert so concurrent refresh jobs cannot race between
        # the existence check and the unique-scope insert.
        acquire_scope_lock()
        codes = sorted({self._subject_code_from_item(item) for item in raw_subjects if isinstance(item, dict) and self._subject_code_from_item(item)})
        subjects = (
            self.db.query(AcademicSubject)
            .filter(func.upper(AcademicSubject.subject_code).in_(codes), func.lower(func.coalesce(AcademicSubject.branch, branch_value)) == branch_value)
            .all()
        ) if codes else []
        by_code = {str(row.subject_code or '').strip().upper(): row for row in subjects}

        now = datetime.utcnow()
        created = 0
        updated = 0
        missing_codes: list[str] = []
        for code in codes:
            subject = by_code.get(code)
            if not subject:
                missing_codes.append(code)
                continue
            for block in blocks:
                delivery = (
                    self.db.query(AcademicSubjectDelivery)
                    .filter(
                        AcademicSubjectDelivery.subject_id == subject.id,
                        AcademicSubjectDelivery.term_id == term.id,
                        AcademicSubjectDelivery.block_id == block.id,
                        func.lower(AcademicSubjectDelivery.branch) == branch_value,
                    )
                    .first()
                )
                if not delivery:
                    delivery = AcademicSubjectDelivery(
                        subject_id=subject.id,
                        term_id=term.id,
                        block_id=block.id,
                        branch=branch_value,
                        learning_platform=None,
                        active=True,
                        configuration_source='ap_catalog',
                        configured_by=None,
                        configured_at=None,
                        catalog_refreshed_at=now,
                        metadata_json={
                            'catalog_source': 'ap.cms.get-subject-cms',
                            'catalog_term_name': term.term_name,
                            'catalog_actor': actor,
                        },
                    )
                    self.db.add(delivery)
                    created += 1
                else:
                    metadata = dict(delivery.metadata_json or {}) if isinstance(delivery.metadata_json, dict) else {}
                    metadata.update({'catalog_source': 'ap.cms.get-subject-cms', 'catalog_term_name': term.term_name, 'catalog_actor': actor})
                    delivery.active = True
                    delivery.catalog_refreshed_at = now
                    delivery.metadata_json = json_safe_value(metadata)
                    delivery.updated_at = now
                    self.db.add(delivery)
                    updated += 1
        self.db.commit()
        return {
            'ok': True,
            'term_id': term.id,
            'term_name': term.term_name,
            'block_ids': [block.id for block in blocks],
            'block_names': [block.block_name for block in blocks],
            'branch': branch_value,
            'ap_subject_count': len(codes),
            'subject_imported_count': int(counters.subjects or 0),
            'delivery_created': created,
            'delivery_updated': updated,
            'missing_subject_codes': missing_codes[:100],
            'catalog_refreshed_at': now.isoformat(),
        }

    def delivery_for_class(self, class_row: AcademicClass) -> AcademicSubjectDelivery | None:
        if not class_row.block_id:
            return None
        branch_value = self.normalize_branch(class_row.branch)
        return (
            self.db.query(AcademicSubjectDelivery)
            .filter(
                AcademicSubjectDelivery.subject_id == class_row.subject_id,
                AcademicSubjectDelivery.term_id == class_row.term_id,
                AcademicSubjectDelivery.block_id == class_row.block_id,
                func.lower(AcademicSubjectDelivery.branch) == branch_value,
                AcademicSubjectDelivery.active.is_(True),
            )
            .first()
        )

    def assert_cms_workflow_allowed_for_class(self, class_id: str, *, job_type: str | None = None) -> None:
        class_row = self.db.get(AcademicClass, class_id)
        if not class_row:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp.')
        delivery = self.delivery_for_class(class_row)
        if delivery and delivery.learning_platform == 'udemy':
            operation = 'đồng bộ CMS/Open edX' if job_type in self.CMS_JOB_TYPES or not job_type else job_type
            raise HTTPException(
                status_code=409,
                detail=f'Môn của lớp {class_row.class_code} đang được chọn là Udemy. Không thể chạy {operation}; AP vẫn được dùng để đồng bộ lớp, giảng viên và sinh viên.',
            )

    def is_subject_udemy_only(self, *, term_id: str, subject_id: str, branch: str | None = None) -> bool:
        query = self.db.query(AcademicSubjectDelivery).filter(
            AcademicSubjectDelivery.term_id == term_id,
            AcademicSubjectDelivery.subject_id == subject_id,
            AcademicSubjectDelivery.active.is_(True),
        )
        if branch:
            query = query.filter(func.lower(AcademicSubjectDelivery.branch) == self.normalize_branch(branch))
        rows = query.all()
        return bool(rows) and all(row.learning_platform == 'udemy' for row in rows)

    def assert_subject_course_mapping_allowed(self, *, term_id: str, subject_id: str, branch: str | None = None) -> None:
        if self.is_subject_udemy_only(term_id=term_id, subject_id=subject_id, branch=branch):
            raise HTTPException(status_code=409, detail='Môn đang được chọn là Udemy ở toàn bộ Block của học kỳ. Không tạo hoặc auto map Course CMS.')

    def cms_eligible_class_ids(self, class_ids: list[str]) -> list[str]:
        if not class_ids:
            return []
        rows = self.db.query(AcademicClass).filter(AcademicClass.id.in_(class_ids)).all()
        return [row.id for row in rows if not ((delivery := self.delivery_for_class(row)) and delivery.learning_platform == 'udemy')]
