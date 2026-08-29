from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, case, func, inspect, literal, literal_column, or_, text
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

    def _previous_term(self, term: AcademicTerm, branch: str) -> AcademicTerm | None:
        candidates = (
            self.db.query(AcademicTerm)
            .filter(
                AcademicTerm.id != term.id,
                func.lower(func.coalesce(AcademicTerm.branch, branch)) == branch,
            )
            .all()
        )
        if term.start_date:
            candidates = [
                item for item in candidates
                if (item.start_date and item.start_date < term.start_date)
                or (item.end_date and item.end_date <= term.start_date)
            ]
        else:
            candidates = [item for item in candidates if item.created_at <= term.created_at]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                item.start_date or item.end_date or item.created_at,
                item.created_at,
                str(item.term_name or item.term_code or ''),
            ),
        )

    def _previous_term_platforms(
        self,
        *,
        term: AcademicTerm,
        branch: str,
        subject_ids: list[str],
    ) -> tuple[AcademicTerm | None, dict[str, str]]:
        previous_term = self._previous_term(term, branch)
        if not previous_term or not subject_ids:
            return previous_term, {}
        rows = (
            self.db.query(AcademicSubjectDelivery.subject_id, AcademicSubjectDelivery.learning_platform)
            .filter(
                AcademicSubjectDelivery.term_id == previous_term.id,
                AcademicSubjectDelivery.subject_id.in_(subject_ids),
                func.lower(AcademicSubjectDelivery.branch) == branch,
                AcademicSubjectDelivery.active.is_(True),
            )
            .all()
        )
        values_by_subject: dict[str, set[str | None]] = {}
        for subject_id, platform in rows:
            values_by_subject.setdefault(subject_id, set()).add(platform)
        inherited: dict[str, str] = {}
        for subject_id, values in values_by_subject.items():
            if len(values) == 1:
                platform = next(iter(values))
                if platform in {'cms', 'udemy'}:
                    inherited[subject_id] = platform
        return previous_term, inherited

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
        management_scope: str | None = None,
    ) -> dict[str, Any]:
        scope_mode = str(management_scope or 'delivery').strip().lower()
        if scope_mode not in {'delivery', 'term'}:
            raise HTTPException(status_code=422, detail='management_scope chỉ nhận delivery hoặc term.')
        if str(learning_platform or '').strip().lower() == 'mixed':
            platform_filter: str | None = 'mixed'
        else:
            platform_filter = self.normalize_platform(learning_platform) if learning_platform not in {None, '', 'all'} else 'all'
        branch_value = self.normalize_branch(branch) if branch else None

        # Reuse the exact same SQL expression in SELECT and GROUP BY. Creating
        # two COALESCE expressions with Python string literals makes SQLAlchemy
        # generate different bind parameters; PostgreSQL then rejects the query
        # because the selected expression is not textually identical to GROUP BY.
        class_branch_key = func.lower(func.coalesce(AcademicClass.branch, literal_column("''")))
        class_counts = (
            self.db.query(
                AcademicClass.subject_id.label('subject_id'),
                AcademicClass.term_id.label('term_id'),
                AcademicClass.block_id.label('block_id'),
                class_branch_key.label('branch_key'),
                func.count(AcademicClass.id).label('class_count'),
                func.count(func.distinct(AcademicClass.campus)).label('campus_count'),
            )
            .filter(AcademicClass.active.is_(True))
            .group_by(AcademicClass.subject_id, AcademicClass.term_id, AcademicClass.block_id, class_branch_key)
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
        # In term-management mode the filter must be applied after all Block
        # deliveries are aggregated. Filtering rows here would make a mixed
        # CMS/Udemy subject look falsely consistent.
        if scope_mode != 'term' and platform_filter != 'all':
            if platform_filter is None:
                query = query.filter(AcademicSubjectDelivery.learning_platform.is_(None))
            else:
                query = query.filter(AcademicSubjectDelivery.learning_platform == platform_filter)
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(AcademicSubject.subject_code.ilike(like), AcademicSubject.subject_name.ilike(like)))

        rows = query.order_by(
            AcademicSubject.subject_code.asc(),
            AcademicSubject.subject_name.asc(),
            AcademicBlock.sort_order.asc(),
            AcademicBlock.block_name.asc(),
        ).all()

        detailed_items: list[dict[str, Any]] = []
        for delivery, subject, term, block, class_count, campus_count, plan_id, plan_version, item_count, milestone_count, plan_imported_at, plan_updated_at, progress_student_count, progress_late_count, progress_unmatched_count, last_udemy_import_at in rows:
            detailed_items.append({
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
                'delivery_ids': [delivery.id],
                'block_count': 1,
                'block_names': [block.block_name],
                'platform_consistent': True,
                'platform_values': [delivery.learning_platform],
                'management_scope': 'delivery',
                'block_deliveries': [],
            })

        if scope_mode == 'term':
            grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
            for item in detailed_items:
                key = (item['subject_id'], item['term_id'], self.normalize_branch(item['branch']))
                current = grouped.get(key)
                block_ref = {
                    'id': item['id'],
                    'block_id': item['block_id'],
                    'block_name': item['block_name'],
                    'learning_platform': item['learning_platform'],
                    'class_count': item['class_count'],
                    'campus_count': item['campus_count'],
                    'has_udemy_plan': item['has_udemy_plan'],
                    'udemy_plan_version': item['udemy_plan_version'],
                    'udemy_milestone_count': item['udemy_milestone_count'],
                    'udemy_progress_student_count': item['udemy_progress_student_count'],
                    'udemy_progress_late_count': item['udemy_progress_late_count'],
                    'udemy_progress_unmatched_count': item['udemy_progress_unmatched_count'],
                    'last_udemy_import_at': item['last_udemy_import_at'],
                }
                if current is None:
                    current = dict(item)
                    current.update({
                        'block_id': item['block_id'],
                        'block_name': item['block_name'],
                        'delivery_ids': [],
                        'block_names': [],
                        'block_deliveries': [],
                        'class_count': 0,
                        'campus_count': 0,
                        'udemy_progress_student_count': 0,
                        'udemy_progress_late_count': 0,
                        'udemy_progress_unmatched_count': 0,
                        'udemy_milestone_count': 0,
                        'management_scope': 'term',
                    })
                    grouped[key] = current
                current['delivery_ids'].append(item['id'])
                current['block_names'].append(item['block_name'])
                current['block_deliveries'].append(block_ref)
                current['class_count'] += int(item['class_count'] or 0)
                current['campus_count'] += int(item['campus_count'] or 0)
                current['udemy_progress_student_count'] += int(item['udemy_progress_student_count'] or 0)
                current['udemy_progress_late_count'] += int(item['udemy_progress_late_count'] or 0)
                current['udemy_progress_unmatched_count'] += int(item['udemy_progress_unmatched_count'] or 0)
                current['has_udemy_plan'] = bool(current.get('has_udemy_plan')) or bool(item['has_udemy_plan'])
                current['udemy_milestone_count'] = int(current.get('udemy_milestone_count') or 0) + int(item['udemy_milestone_count'] or 0)
                for field in ('configured_at', 'catalog_refreshed_at', 'udemy_plan_updated_at', 'last_udemy_import_at', 'updated_at'):
                    candidate = item.get(field)
                    if candidate is not None and (current.get(field) is None or candidate > current[field]):
                        current[field] = candidate

            term_items: list[dict[str, Any]] = []
            for current in grouped.values():
                values = {block.get('learning_platform') for block in current['block_deliveries']}
                consistent = len(values) <= 1
                current['platform_consistent'] = consistent
                current['platform_values'] = sorted(values, key=lambda value: '' if value is None else str(value))
                current['learning_platform'] = next(iter(values)) if consistent and values else None
                current['block_count'] = len(current['block_deliveries'])
                current['block_name'] = ', '.join(current['block_names'])
                current['configuration_source'] = 'term_management'
                term_items.append(current)

            if platform_filter != 'all':
                if platform_filter == 'mixed':
                    term_items = [item for item in term_items if not item['platform_consistent']]
                elif platform_filter is None:
                    term_items = [item for item in term_items if item['platform_consistent'] and item['learning_platform'] is None]
                else:
                    term_items = [item for item in term_items if item['platform_consistent'] and item['learning_platform'] == platform_filter]
            all_items = term_items
        else:
            all_items = detailed_items

        total = len(all_items)
        page_value = max(1, int(page or 1))
        page_size_value = max(1, min(200, int(page_size or 50)))
        total_pages = math.ceil(total / page_size_value) if total else 0
        items = all_items[(page_value - 1) * page_size_value:page_value * page_size_value]

        summary = {
            'total': total,
            'cms_count': sum(1 for item in all_items if item.get('platform_consistent', True) and item.get('learning_platform') == 'cms'),
            'udemy_count': sum(1 for item in all_items if item.get('platform_consistent', True) and item.get('learning_platform') == 'udemy'),
            'unassigned_count': sum(1 for item in all_items if item.get('platform_consistent', True) and item.get('learning_platform') is None),
            'mixed_count': sum(1 for item in all_items if not item.get('platform_consistent', True)),
            'class_count': sum(int(item.get('class_count') or 0) for item in all_items),
            'scope_label': 'Theo học kỳ' if scope_mode == 'term' else 'Theo học kỳ và Block',
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
        previous_term, inherited_platforms = self._previous_term_platforms(
            term=term,
            branch=branch_value,
            subject_ids=[row.id for row in subjects],
        )

        now = datetime.utcnow()
        created = 0
        updated = 0
        inherited_delivery_count = 0
        inherited_subject_ids: set[str] = set()
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
                    inherited_platform = inherited_platforms.get(subject.id)
                    metadata: dict[str, Any] = {
                        'catalog_source': 'ap.get-course',
                        'catalog_term_name': term.term_name,
                        'catalog_actor': actor,
                    }
                    configuration_source = 'ap_catalog'
                    configured_at = None
                    if inherited_platform and previous_term:
                        configuration_source = 'previous_term_carry_forward'
                        configured_at = now
                        inherited_delivery_count += 1
                        inherited_subject_ids.add(subject.id)
                        metadata.update({
                            'platform_inherited_from_term_id': previous_term.id,
                            'platform_inherited_from_term_name': previous_term.term_name,
                            'platform_history': [{
                                'from': None,
                                'to': inherited_platform,
                                'source': 'previous_term_carry_forward',
                                'actor': actor,
                                'changed_at': now.isoformat(),
                            }],
                            'platform_policy_version': 'udemy-subject-management/batch35.2',
                        })
                    delivery = AcademicSubjectDelivery(
                        subject_id=subject.id,
                        term_id=term.id,
                        block_id=block.id,
                        branch=branch_value,
                        learning_platform=inherited_platform,
                        active=True,
                        configuration_source=configuration_source,
                        configured_by=actor if inherited_platform else None,
                        configured_at=configured_at,
                        catalog_refreshed_at=now,
                        metadata_json=json_safe_value(metadata),
                    )
                    self.db.add(delivery)
                    created += 1
                else:
                    metadata = dict(delivery.metadata_json or {}) if isinstance(delivery.metadata_json, dict) else {}
                    metadata.update({'catalog_source': 'ap.get-course', 'catalog_term_name': term.term_name, 'catalog_actor': actor})
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
            'previous_term_id': previous_term.id if previous_term else None,
            'previous_term_name': previous_term.term_name if previous_term else None,
            'inherited_subject_count': len(inherited_subject_ids),
            'inherited_delivery_count': inherited_delivery_count,
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
