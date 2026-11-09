"""Bounded read model for AP; never loads logs, evidence or invokes sync jobs."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import (
    AcademicBlock, AcademicClass, AcademicClassStudent, AcademicStudent, AcademicSubject, AcademicTerm,
)
from app.models.learning_analytics import AnalyticsLearningBehaviorSnapshot as Snapshot
from app.services.academic_service import AcademicService
from app.services.learning_analytics.presentation import behavior_freshness

DISCLAIMER = 'Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.'
RESULT_FIELDS = (
    'classification', 'display_label', 'confidence_score', 'reason_codes',
    'human_readable_summary', 'recommended_action', 'data_quality', 'calculated_at', 'last_activity_at',
)


class APLearningResultsService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_class(self, *, ap_class_id, ap_term_id, branch, campus, subject_code, ap_block_id=None):
        q = self.db.query(AcademicClass, AcademicBlock.ap_block_id).join(
            AcademicTerm, AcademicTerm.id == AcademicClass.term_id,
        ).join(AcademicSubject, AcademicSubject.id == AcademicClass.subject_id).outerjoin(
            AcademicBlock, AcademicBlock.id == AcademicClass.block_id,
        ).filter(
            AcademicClass.ap_class_id == ap_class_id, AcademicClass.active.is_(True),
            AcademicClass.branch == branch, AcademicClass.campus == campus,
            AcademicTerm.ap_term_id == ap_term_id, AcademicTerm.branch == branch,
            AcademicSubject.subject_code == subject_code, AcademicSubject.branch == branch,
        )
        if ap_block_id is not None:
            q = q.filter(AcademicBlock.ap_block_id == ap_block_id)
        rows = q.limit(2).all()
        if not rows:
            raise HTTPException(status_code=404, detail='AP_CLASS_NOT_FOUND')
        if len(rows) != 1:
            raise HTTPException(status_code=409, detail='AP_CLASS_AMBIGUOUS')
        cls, block_id = rows[0]
        mapping = AcademicService(self.db).effective_course_mapping_for_class(cls)
        course = str(mapping.openedx_course_id or '').strip() if mapping else ''
        if not course:
            raise HTTPException(status_code=409, detail='COURSE_MAPPING_MISSING')
        return cls, dict(ap_class_id=ap_class_id, ap_term_id=ap_term_id, ap_block_id=block_id,
                         branch=branch, campus=campus, subject_code=subject_code, course_id=course)

    def _query(self, cls, context):
        # Match the analytics canonical username policy while refusing duplicate aliases.
        identities = self.db.query(
            func.lower(func.trim(Snapshot.username)).label('username'),
            func.max(Snapshot.id).label('snapshot_id'), func.count(Snapshot.id).label('matches'),
        ).filter(Snapshot.class_id == cls.id, Snapshot.course_id == context['course_id']).group_by(
            func.lower(func.trim(Snapshot.username)),
        ).subquery()
        roster_identities = self.db.query(
            func.lower(func.trim(AcademicStudent.username)).label('username'),
            func.count(AcademicStudent.id).label('roster_matches'),
        ).join(AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id == cls.id, AcademicStudent.active.is_(True),
        ).group_by(func.lower(func.trim(AcademicStudent.username))).subquery()
        return self.db.query(AcademicStudent).join(
            AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id,
        ).join(roster_identities, roster_identities.c.username == func.lower(func.trim(AcademicStudent.username))
        ).outerjoin(identities, identities.c.username == func.lower(func.trim(AcademicStudent.username))).outerjoin(
            Snapshot, Snapshot.id == identities.c.snapshot_id,
        ).filter(AcademicClassStudent.class_id == cls.id, AcademicStudent.active.is_(True)), identities, roster_identities

    @staticmethod
    def _serialize(row):
        data = dict(row._mapping)
        exists = data.pop('snapshot_id') is not None
        if data.pop('matches') not in (None, 1) or data.pop('roster_matches') != 1:
            raise HTTPException(status_code=409, detail='ANALYTICS_IDENTITY_AMBIGUOUS')
        if not exists:
            return dict(student_code=data['student_code'], full_name=data['full_name'], status='missing',
                        classification=None, display_label='Chưa có kết quả phân tích', confidence_score=None,
                        reason_codes=['MISSING_BEHAVIOR_SNAPSHOT'], human_readable_summary='',
                        recommended_action='INSUFFICIENT_DATA_RECHECK_LATER', data_quality='MISSING',
                        calculated_at=None, last_activity_at=None, snapshot_stale=True)
        freshness = behavior_freshness(SimpleNamespace(**data), stale_hours=settings.analytics_snapshot_stale_hours)
        data['reason_codes'] = freshness['reason_codes']
        for field in ('calculated_at', 'last_activity_at'):
            value = data[field]
            if value and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            data[field] = value.isoformat() if value else None
        return dict(**data, status='stale' if freshness['snapshot_stale'] else 'ready',
                    snapshot_stale=freshness['snapshot_stale'])

    def _page(self, q, identities, roster_identities, *, limit, offset):
        return [self._serialize(row) for row in q.with_entities(
            AcademicStudent.student_code, AcademicStudent.full_name,
            Snapshot.id.label('snapshot_id'), identities.c.matches, roster_identities.c.roster_matches,
            *(getattr(Snapshot, field) for field in RESULT_FIELDS),
        ).order_by(AcademicStudent.student_code.asc(), AcademicStudent.id.asc()).limit(limit).offset(offset).all()]

    def class_results(self, *, limit=100, offset=0, **scope):
        cls, context = self.resolve_class(**scope)
        q, identities, roster_identities = self._query(cls, context)
        cutoff = datetime.utcnow() - timedelta(hours=max(1, settings.analytics_snapshot_stale_hours))
        groups = q.with_entities(
            Snapshot.classification, func.count(AcademicStudent.id), func.count(Snapshot.id),
            func.sum(case((and_(Snapshot.id.is_not(None), Snapshot.calculated_at < cutoff), 1), else_=0)),
            func.max(identities.c.matches), func.max(roster_identities.c.roster_matches),
        ).group_by(Snapshot.classification).all()
        total = snapshots = stale = 0
        counts = {}
        for classification, size, present, old, matches, roster_matches in groups:
            if (matches and matches > 1) or roster_matches > 1:
                raise HTTPException(status_code=409, detail='ANALYTICS_IDENTITY_AMBIGUOUS')
            total += size
            snapshots += present
            stale += old
            if classification is not None:
                counts[classification] = size
        summary = dict(roster_count=total, snapshot_count=snapshots, missing_snapshot_count=total-snapshots,
                       stale_snapshot_count=stale, classification_counts=counts,
                       data_status='not_calculated' if not snapshots else 'partial' if snapshots < total or stale else 'ready')
        return dict(context=context, summary=summary, total=total, limit=limit, offset=offset,
                    next_offset=offset+limit if offset+limit < total else None,
                    items=self._page(q, identities, roster_identities, limit=limit, offset=offset), disclaimer=DISCLAIMER)

    def student_result(self, *, student_code, **scope):
        cls, context = self.resolve_class(**scope)
        q, identities, roster_identities = self._query(cls, context)
        rows = self._page(q.filter(AcademicStudent.student_code == student_code), identities, roster_identities, limit=2, offset=0)
        if not rows:
            raise HTTPException(status_code=404, detail='AP_STUDENT_NOT_FOUND')
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail='AP_STUDENT_AMBIGUOUS')
        return dict(context=context, result=rows[0], disclaimer=DISCLAIMER)
