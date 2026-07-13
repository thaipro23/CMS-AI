from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
import io

from sqlalchemy import case, func

from app.core.config import settings

from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob, AcademicCourseMapping, AcademicSubject, AcademicTerm
from app.models.learning_analytics import (
    AnalyticsCourseSession,
    AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentSessionProgress,
    AnalyticsStudentVideoProgress,
    AnalyticsTrackingEvent,
)
from app.services.academic_service import AcademicService


class LearningAnalyticsResultsWorkflowService:
    """Read-only learning result, evidence drawer and class diagnostics workflow split."""

    def __init__(self, parent: Any):
        self.parent = parent
        self.db = parent.db

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parent, name)

    def learning_dashboard(self, *, campus: str | None = None, branch: str | None = None, course_id: str | None = None, class_id: str | None = None, classification: str | None = None, date_from: str | None = None, date_to: str | None = None, limit: int = 50, allowed_class_ids: set[str] | None = None) -> dict[str, Any]:
        q = self._apply_behavior_common_filters(
            self.db.query(AnalyticsLearningBehaviorSnapshot),
            campus=campus,
            branch=branch,
            course_id=course_id,
            class_id=class_id,
            classification=classification,
            date_from=date_from,
            date_to=date_to,
            allowed_class_ids=allowed_class_ids,
        )
        rows = q.all()
        counts = Counter(r.classification for r in rows)
        quality = Counter(r.data_quality for r in rows)
        class_ids = sorted({r.class_id for r in rows if r.class_id})
        classes = {c.id: c for c in self.db.query(AcademicClass).filter(AcademicClass.id.in_(class_ids)).all()} if class_ids else {}
        by_class: dict[str, list[AnalyticsLearningBehaviorSnapshot]] = defaultdict(list)
        for row in rows:
            by_class[str(row.class_id or '')].append(row)
        class_items: list[dict[str, Any]] = []
        for cid, group in by_class.items():
            cls = classes.get(cid)
            cc = Counter(r.classification for r in group)
            class_items.append({
                'class_id': cid,
                'class_code': cls.class_code if cls else cid,
                'class_name': cls.class_name if cls else '',
                'campus': cls.campus if cls else None,
                'branch': cls.branch if cls else None,
                'course_id': group[0].course_id if group else None,
                'total_students': len(group),
                'likely_real_learning_count': cc.get('LIKELY_REAL_LEARNING', 0),
                'possible_idle_count': cc.get('POSSIBLE_IDLE', 0),
                'possible_suspicious_count': cc.get('POSSIBLE_ANOMALY', 0) + cc.get('POSSIBLE_CHEATING', 0),
                'insufficient_data_count': cc.get('INSUFFICIENT_DATA', 0),
                'normal_count': cc.get('NORMAL', 0),
                'avg_confidence_score': round(sum(float(r.confidence_score or 0) for r in group) / len(group), 2) if group else 0,
                'avg_deadline_compliance_percent': round(sum(float(r.deadline_compliance_percent or 0) for r in group if r.deadline_compliance_percent is not None) / max(1, len([r for r in group if r.deadline_compliance_percent is not None])), 2) if group else None,
            })
        class_items.sort(key=lambda item: (item['possible_suspicious_count'], item['possible_idle_count']), reverse=True)
        top_suspicious = sorted(rows, key=lambda r: (float(r.suspicious_score or 0), float(r.confidence_score or 0)), reverse=True)[:limit]
        top_idle = sorted(rows, key=lambda r: (float(r.idle_score or 0), float(r.confidence_score or 0)), reverse=True)[:limit]
        overdue = [r for r in rows if (r.crammed_session_count or 0) > 0 or (r.deadline_compliance_percent is not None and r.deadline_compliance_percent < 60)]
        def row_item(r: AnalyticsLearningBehaviorSnapshot) -> dict[str, Any]:
            cls = classes.get(str(r.class_id or ''))
            return {
                'class_id': r.class_id,
                'class_code': cls.class_code if cls else r.class_id,
                'campus': cls.campus if cls else None,
                'course_id': r.course_id,
                'username': r.username,
                'classification': r.classification,
                'display_label': self._safe_label(r.classification, r.display_label),
                'confidence_score': r.confidence_score,
                'real_learning_score': r.real_learning_score,
                'idle_score': r.idle_score,
                'suspicious_score': r.suspicious_score,
                'deadline_compliance_percent': r.deadline_compliance_percent,
                'crammed_session_count': r.crammed_session_count,
                'quiz_before_video_count': r.quiz_before_video_count,
                'reason_codes': r.reason_codes or [],
                'human_readable_summary': r.human_readable_summary,
                'recommended_action': self._recommended_action_label(r.recommended_action),
                'data_quality': r.data_quality,
                'last_activity_at': r.last_activity_at.isoformat() if r.last_activity_at else None,
                'calculated_at': r.calculated_at.isoformat() if r.calculated_at else None,
            }
        return {
            'filters': {'campus': campus, 'branch': branch, 'course_id': course_id, 'class_id': class_id, 'classification': classification or 'all', 'date_from': date_from, 'date_to': date_to},
            'total_students': len(rows),
            'likely_real_learning_count': counts.get('LIKELY_REAL_LEARNING', 0),
            'possible_idle_count': counts.get('POSSIBLE_IDLE', 0),
            'possible_suspicious_count': counts.get('POSSIBLE_ANOMALY', 0) + counts.get('POSSIBLE_CHEATING', 0),
            'insufficient_data_count': counts.get('INSUFFICIENT_DATA', 0),
            'normal_count': counts.get('NORMAL', 0),
            'data_quality_breakdown': dict(quality),
            'class_items': class_items[:limit],
            'top_possible_suspicious': [row_item(r) for r in top_suspicious if r.classification in {'POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING'} or (r.suspicious_score or 0) > 0],
            'top_possible_idle': [row_item(r) for r in top_idle if r.classification == 'POSSIBLE_IDLE' or (r.idle_score or 0) > 0],
            'deadline_attention': [row_item(r) for r in sorted(overdue, key=lambda r: (r.crammed_session_count or 0, 100 - float(r.deadline_compliance_percent or 0)), reverse=True)[:limit]],
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.',
        }

    def export_learning_behavior_csv(self, *, campus: str | None = None, branch: str | None = None, course_id: str | None = None, class_id: str | None = None, classification: str | None = None, date_from: str | None = None, date_to: str | None = None, allowed_class_ids: set[str] | None = None) -> str:
        import csv
        import io
        # Re-query rows directly; dashboard top lists are intentionally capped.
        q = self._apply_behavior_common_filters(
            self.db.query(AnalyticsLearningBehaviorSnapshot),
            campus=campus,
            branch=branch,
            course_id=course_id,
            class_id=class_id,
            classification=classification,
            date_from=date_from,
            date_to=date_to,
            allowed_class_ids=allowed_class_ids,
        )
        max_rows = int(getattr(settings, 'analytics_export_max_rows', 50000) or 50000)
        rows = q.order_by(AnalyticsLearningBehaviorSnapshot.class_id.asc(), AnalyticsLearningBehaviorSnapshot.username.asc()).limit(max_rows).all()
        class_ids = sorted({r.class_id for r in rows if r.class_id})
        classes = {c.id: c for c in self.db.query(AcademicClass).filter(AcademicClass.id.in_(class_ids)).all()} if class_ids else {}
        output = io.StringIO()
        output.write('Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.\n')
        output.write(f'Giới hạn xuất tối đa {max_rows} dòng để bảo vệ hệ thống production.\n')
        writer = csv.writer(output)
        writer.writerow(['class_id', 'class_code', 'campus', 'course_id', 'username', 'classification_display', 'confidence_score', 'real_learning_score', 'idle_score', 'suspicious_score', 'deadline_compliance_percent', 'crammed_session_count', 'quiz_before_video_count', 'reason_summary', 'recommended_action', 'data_quality', 'calculated_at'])
        for r in rows:
            cls = classes.get(str(r.class_id or ''))
            writer.writerow([
                r.class_id or '',
                cls.class_code if cls else '',
                cls.campus if cls else '',
                r.course_id,
                r.username,
                self._safe_label(r.classification, r.display_label),
                r.confidence_score,
                r.real_learning_score,
                r.idle_score,
                r.suspicious_score,
                r.deadline_compliance_percent if r.deadline_compliance_percent is not None else '',
                r.crammed_session_count,
                r.quiz_before_video_count,
                '; '.join(r.reason_codes or []),
                self._recommended_action_label(r.recommended_action),
                r.data_quality,
                r.calculated_at.isoformat() if r.calculated_at else '',
            ])
        return output.getvalue()

    def video_students(self, *, video_id: str, course_id: str | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        q = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.video_id == video_id)
        if course_id:
            q = q.filter(AnalyticsStudentVideoProgress.course_id == course_id)
        total = q.count()
        rows = q.order_by(AnalyticsStudentVideoProgress.is_suspicious.desc(), AnalyticsStudentVideoProgress.completion_percent.desc().nullslast()).offset(max(0, offset)).limit(min(max(1, limit), 200)).all()
        return {
            'video_id': video_id,
            'course_id': course_id,
            'total': total,
            'items': [
                {
                    'username': r.username,
                    'course_id': r.course_id,
                    'session_index': r.session_index,
                    'completion_percent': r.completion_percent,
                    'estimated_watch_seconds': r.estimated_watch_seconds,
                    'estimated_watch_percent': r.estimated_watch_percent,
                    'is_completed': r.is_completed,
                    'is_suspicious': r.is_suspicious,
                    'suspicious_reason': r.suspicious_reason,
                    'first_played_at': r.first_played_at.isoformat() if r.first_played_at else None,
                    'last_event_at': r.last_event_at.isoformat() if r.last_event_at else None,
                }
                for r in rows
            ],
        }

    def student_behavior_detail(self, *, class_id: str | None, course_id: str | None, username: str) -> dict[str, Any]:
        behavior = None
        if course_id:
            behavior = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(
                AnalyticsLearningBehaviorSnapshot.class_id == class_id,
                AnalyticsLearningBehaviorSnapshot.course_id == course_id,
                AnalyticsLearningBehaviorSnapshot.username == username,
            ).first()
        session_q = self.db.query(AnalyticsStudentSessionProgress).filter(AnalyticsStudentSessionProgress.username == username)
        video_q = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.username == username)
        if course_id:
            session_q = session_q.filter(AnalyticsStudentSessionProgress.course_id == course_id)
            video_q = video_q.filter(AnalyticsStudentVideoProgress.course_id == course_id)
        session_rows = session_q.order_by(AnalyticsStudentSessionProgress.week_index.asc().nullslast(), AnalyticsStudentSessionProgress.session_index.asc()).all()
        video_rows = video_q.order_by(AnalyticsStudentVideoProgress.session_index.asc().nullslast(), AnalyticsStudentVideoProgress.last_event_at.desc().nullslast()).limit(300).all()
        return {
            'behavior': None if not behavior else {
                'username': behavior.username,
                'user_id': behavior.user_id,
                'course_id': behavior.course_id,
                'class_id': behavior.class_id,
                'classification': behavior.classification,
                'display_label': behavior.display_label,
                'confidence_score': behavior.confidence_score,
                'real_learning_score': behavior.real_learning_score,
                'idle_score': behavior.idle_score,
                'suspicious_score': behavior.suspicious_score,
                'deadline_compliance_percent': behavior.deadline_compliance_percent,
                'crammed_session_count': behavior.crammed_session_count,
                'quiz_before_video_count': behavior.quiz_before_video_count,
                'reason_codes': behavior.reason_codes or [],
                'human_readable_summary': behavior.human_readable_summary,
                'recommended_action': behavior.recommended_action,
                'data_quality': behavior.data_quality,
                'calculated_at': behavior.calculated_at.isoformat() if behavior.calculated_at else None,
                'last_activity_at': behavior.last_activity_at.isoformat() if behavior.last_activity_at else None,
            },
            'sessions': [
                {
                    'session_index': row.session_index,
                    'session_title': row.session_title,
                    'week_index': row.week_index,
                    'deadline_at': row.deadline_at.isoformat() if row.deadline_at else None,
                    'deadline_source': row.deadline_source,
                    'total_videos': row.total_videos,
                    'videos_seen': row.videos_seen,
                    'videos_completed': row.videos_completed,
                    'avg_video_completion_percent': row.avg_video_completion_percent,
                    'estimated_watch_seconds': row.estimated_watch_seconds,
                    'quiz_attempted': row.quiz_attempted,
                    'quiz_completed': row.quiz_completed,
                    'quiz_score': row.quiz_score,
                    'started_at': row.started_at.isoformat() if row.started_at else None,
                    'last_activity_at': row.last_activity_at.isoformat() if row.last_activity_at else None,
                    'completed_before_deadline': row.completed_before_deadline,
                    'completed_late': row.completed_late,
                    'session_learning_status': row.session_learning_status,
                    'reason_codes': row.reason_codes or [],
                    'evidence': row.evidence_json or {},
                }
                for row in session_rows
            ],
            'videos': [
                {
                    'video_id': row.video_id,
                    'video_code': row.video_code,
                    'session_index': row.session_index,
                    'component_title': row.component_title,
                    'duration_seconds': row.duration_seconds,
                    'max_position_seconds': row.max_position_seconds,
                    'completion_percent': row.completion_percent,
                    'estimated_watch_seconds': row.estimated_watch_seconds,
                    'estimated_watch_percent': row.estimated_watch_percent,
                    'play_count': row.play_count,
                    'pause_count': row.pause_count,
                    'stop_count': row.stop_count,
                    'seek_count': row.seek_count,
                    'is_completed': row.is_completed,
                    'is_suspicious': row.is_suspicious,
                    'suspicious_reason': row.suspicious_reason,
                    'first_played_at': row.first_played_at.isoformat() if row.first_played_at else None,
                    'last_event_at': row.last_event_at.isoformat() if row.last_event_at else None,
                }
                for row in video_rows
            ],
            'timeline_weeks': self._timeline_weeks_from_sessions(session_rows),
            'disclaimer': 'Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.',
        }

    def class_behavior_overview(
        self,
        *,
        subject_id: str,
        term_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        classification: str | None = None,
        class_id: str | None = None,
        allowed_class_ids: set[str] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return result-first class overview for the learning behavior flow.

        This endpoint intentionally summarizes by class first so the UI can follow
        the operational path: term -> campus -> subject -> class -> student result.
        It reads only snapshot/aggregate tables; it never scans raw tracking logs.
        """
        class_q = self.db.query(AcademicClass).filter(
            AcademicClass.subject_id == subject_id,
            AcademicClass.active.is_(True),
        )
        if term_id:
            class_q = class_q.filter(AcademicClass.term_id == term_id)
        if campus:
            class_q = class_q.filter(func.lower(AcademicClass.campus) == campus.strip().lower())
        if branch:
            class_q = class_q.filter(func.lower(AcademicClass.branch) == branch.strip().lower())
        if class_id:
            class_q = class_q.filter(AcademicClass.id == class_id)
        if allowed_class_ids is not None:
            if not allowed_class_ids:
                return {
                    'total': 0,
                    'items': [],
                    'summary': self._empty_class_behavior_overview_summary(),
                    'classification_filter': classification or 'all',
                    'safe_policy': 'signals_only_not_violation',
                }
            class_q = class_q.filter(AcademicClass.id.in_(allowed_class_ids))

        classes = class_q.order_by(AcademicClass.class_code.asc(), AcademicClass.class_name.asc()).all()
        class_ids = [str(item.id) for item in classes if item.id]
        if not class_ids:
            return {
                'total': 0,
                'items': [],
                'summary': self._empty_class_behavior_overview_summary(),
                'classification_filter': classification or 'all',
                'safe_policy': 'signals_only_not_violation',
            }

        student_counts = {
            str(class_id): int(count or 0)
            for class_id, count in self.db.query(
                AcademicClassStudent.class_id,
                func.count(func.distinct(AcademicClassStudent.student_id)),
            ).filter(AcademicClassStudent.class_id.in_(class_ids)).group_by(AcademicClassStudent.class_id).all()
        }

        class_overrides = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id.in_(class_ids),
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).all()
        override_by_class: dict[str, AcademicClassCourseMapping] = {}
        for mapping in class_overrides:
            override_by_class.setdefault(str(mapping.class_id), mapping)
        inherited_by_class = AcademicService(self.db).inherited_course_mappings_for_classes(classes)

        behavior_rows = self.db.query(
            AnalyticsLearningBehaviorSnapshot.class_id,
            func.count(AnalyticsLearningBehaviorSnapshot.id).label('total_students'),
            func.sum(case((AnalyticsLearningBehaviorSnapshot.classification == 'LIKELY_REAL_LEARNING', 1), else_=0)).label('likely_real_learning_count'),
            func.sum(case((AnalyticsLearningBehaviorSnapshot.classification == 'POSSIBLE_IDLE', 1), else_=0)).label('possible_idle_count'),
            func.sum(case((AnalyticsLearningBehaviorSnapshot.classification.in_(['POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING']), 1), else_=0)).label('possible_suspicious_count'),
            func.sum(case((AnalyticsLearningBehaviorSnapshot.classification == 'INSUFFICIENT_DATA', 1), else_=0)).label('insufficient_data_count'),
            func.sum(case((AnalyticsLearningBehaviorSnapshot.classification == 'NORMAL', 1), else_=0)).label('normal_count'),
            func.max(AnalyticsLearningBehaviorSnapshot.last_activity_at).label('last_activity_at'),
            func.max(AnalyticsLearningBehaviorSnapshot.calculated_at).label('calculated_at'),
        ).filter(
            AnalyticsLearningBehaviorSnapshot.class_id.in_(class_ids),
        ).group_by(AnalyticsLearningBehaviorSnapshot.class_id).all()

        behavior_by_class: dict[str, dict[str, Any]] = {}
        for row in behavior_rows:
            class_id = str(row.class_id)
            behavior_by_class[class_id] = {
                'total_students': int(row.total_students or 0),
                'likely_real_learning_count': int(row.likely_real_learning_count or 0),
                'possible_idle_count': int(row.possible_idle_count or 0),
                'possible_suspicious_count': int(row.possible_suspicious_count or 0),
                'insufficient_data_count': int(row.insufficient_data_count or 0),
                'normal_count': int(row.normal_count or 0),
                'last_activity_at': row.last_activity_at.isoformat() if row.last_activity_at else None,
                'calculated_at': row.calculated_at.isoformat() if row.calculated_at else None,
            }

        normalized_filter = (classification or 'all').strip().upper()
        if normalized_filter == 'ALL':
            normalized_filter = 'all'

        items: list[dict[str, Any]] = []
        totals = Counter()
        for klass in classes:
            class_id = str(klass.id)
            raw_behavior = behavior_by_class.get(class_id) or self._empty_class_behavior_overview_summary()
            student_count = int(student_counts.get(class_id, 0))
            snapshot_count = int(raw_behavior.get('total_students') or 0)
            missing_snapshot_count = max(0, student_count - snapshot_count)
            behavior = dict(raw_behavior)
            if missing_snapshot_count:
                behavior['total_students'] = max(student_count, snapshot_count)
                behavior['insufficient_data_count'] = int(behavior.get('insufficient_data_count') or 0) + missing_snapshot_count
            focus_count = self._class_behavior_focus_count(behavior, normalized_filter)
            if normalized_filter != 'all' and focus_count <= 0:
                continue
            dominant = self._dominant_classification(behavior)
            data_status = 'ready' if snapshot_count >= student_count and student_count > 0 else ('partial' if snapshot_count > 0 else 'not_calculated')
            mapping = override_by_class.get(class_id) or inherited_by_class.get(class_id)
            item = {
                'class_id': class_id,
                'class_code': klass.class_code,
                'class_name': klass.class_name,
                'campus': klass.campus,
                'branch': klass.branch,
                'openedx_course_id': mapping.openedx_course_id if mapping else None,
                'openedx_mapping_source': 'class_override' if class_id in override_by_class else ('subject_term_mapping' if mapping else None),
                'student_count': student_count,
                'roster_count': student_count,
                'snapshot_count': snapshot_count,
                'missing_snapshot_count': missing_snapshot_count,
                'likely_real_learning_count': int(behavior.get('likely_real_learning_count') or 0),
                'possible_idle_count': int(behavior.get('possible_idle_count') or 0),
                'possible_suspicious_count': int(behavior.get('possible_suspicious_count') or 0),
                'insufficient_data_count': int(behavior.get('insufficient_data_count') or 0),
                'normal_count': int(behavior.get('normal_count') or 0),
                'focus_count': int(focus_count),
                'dominant_classification': dominant,
                'dominant_label': self._safe_label(dominant, ''),
                'data_status': data_status,
                'last_activity_at': behavior.get('last_activity_at'),
                'calculated_at': behavior.get('calculated_at'),
            }
            items.append(item)
            totals['total_classes'] += 1
            totals['total_students'] += student_count
            totals['roster_count'] += item['roster_count']
            totals['snapshot_count'] += item['snapshot_count']
            totals['missing_snapshot_count'] += item['missing_snapshot_count']
            totals['likely_real_learning_count'] += item['likely_real_learning_count']
            totals['possible_idle_count'] += item['possible_idle_count']
            totals['possible_suspicious_count'] += item['possible_suspicious_count']
            totals['insufficient_data_count'] += item['insufficient_data_count']
            totals['normal_count'] += item['normal_count']
            totals['not_calculated_class_count'] += 1 if data_status == 'not_calculated' else 0

        total = len(items)
        safe_limit = min(max(1, int(limit or 500)), 500)
        safe_offset = max(0, int(offset or 0))
        return {
            'total': total,
            'items': items[safe_offset:safe_offset + safe_limit],
            'summary': {
                'total_classes': int(totals.get('total_classes', 0)),
                'total_students': int(totals.get('total_students', 0)),
                'roster_count': int(totals.get('roster_count', 0)),
                'snapshot_count': int(totals.get('snapshot_count', 0)),
                'missing_snapshot_count': int(totals.get('missing_snapshot_count', 0)),
                'likely_real_learning_count': int(totals.get('likely_real_learning_count', 0)),
                'possible_idle_count': int(totals.get('possible_idle_count', 0)),
                'possible_suspicious_count': int(totals.get('possible_suspicious_count', 0)),
                'insufficient_data_count': int(totals.get('insufficient_data_count', 0)),
                'normal_count': int(totals.get('normal_count', 0)),
                'not_calculated_class_count': int(totals.get('not_calculated_class_count', 0)),
            },
            'classification_filter': normalized_filter,
            'safe_policy': 'signals_only_not_violation',
        }

    def analytics_course_class_mapping_reliability_report(
        self,
        *,
        campus: str | None = None,
        branch: str | None = None,
        term_id: str | None = None,
        subject_id: str | None = None,
        class_id: str | None = None,
        course_id: str | None = None,
        allowed_class_ids: set[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Read-only class/course mapping reliability report for analytics.

        Post-ingest recalculation depends on resolving tracking.log course IDs to
        the correct AP class. This report exposes the mapping evidence before an
        operator runs broad backfill. It uses existing mapping, roster, event,
        progress and snapshot tables only; it never creates mappings, enqueues
        jobs, scans raw tracking.log, or recalculates snapshots in the request.
        """
        safe_limit = max(1, min(int(limit or 50), 500))
        clean_campus = str(campus or '').strip()
        clean_branch = str(branch or '').strip()
        clean_term_id = str(term_id or '').strip()
        clean_subject_id = str(subject_id or '').strip()
        clean_class_id = str(class_id or '').strip()
        clean_course_id = str(course_id or '').strip()

        q = self.db.query(AcademicClass).filter(AcademicClass.active.is_(True))
        if allowed_class_ids is not None:
            if not allowed_class_ids:
                q = q.filter(False)
            else:
                q = q.filter(AcademicClass.id.in_(sorted(allowed_class_ids)))
        if clean_class_id:
            q = q.filter(AcademicClass.id == clean_class_id)
        if clean_term_id:
            q = q.filter(AcademicClass.term_id == clean_term_id)
        if clean_subject_id:
            q = q.filter(AcademicClass.subject_id == clean_subject_id)
        if clean_campus:
            q = q.filter(func.lower(AcademicClass.campus) == clean_campus.lower())
        if clean_branch:
            q = q.filter(func.lower(AcademicClass.branch) == clean_branch.lower())

        total_scope_classes = int(q.count() or 0)
        classes = q.order_by(AcademicClass.campus.asc().nullslast(), AcademicClass.class_code.asc()).limit(safe_limit).all()
        subject_ids = {str(item.subject_id) for item in classes if getattr(item, 'subject_id', None)}
        term_ids = {str(item.term_id) for item in classes if getattr(item, 'term_id', None)}
        subjects = {row.id: row for row in self.db.query(AcademicSubject).filter(AcademicSubject.id.in_(list(subject_ids))).all()} if subject_ids else {}
        terms = {row.id: row for row in self.db.query(AcademicTerm).filter(AcademicTerm.id.in_(list(term_ids))).all()} if term_ids else {}

        rows: list[dict[str, Any]] = []
        counters: Counter[str] = Counter()
        unresolved_course_ids: set[str] = set()
        resolved_course_ids: set[str] = set()

        for cls in classes:
            mapping = self._class_course_mapping_diagnostics(class_id=cls.id, preferred_course_id=clean_course_id or None)
            resolved_course_id = str(mapping.get('resolved_course_id') or '').strip()
            mapping_status = str(mapping.get('status') or 'missing')
            subject = subjects.get(cls.subject_id)
            term = terms.get(cls.term_id)

            roster_count = int(self.db.query(AcademicClassStudent.id).filter(AcademicClassStudent.class_id == cls.id).count() or 0)
            event_count = 0
            event_user_count = 0
            latest_event_at = None
            snapshot_count = 0
            latest_snapshot_at = None
            video_progress_count = 0
            session_progress_count = 0
            course_session_count = 0
            if resolved_course_id:
                resolved_course_ids.add(resolved_course_id)
                event_q = self.db.query(AnalyticsTrackingEvent).filter(AnalyticsTrackingEvent.course_id == resolved_course_id)
                event_count = int(event_q.count() or 0)
                event_user_count = int(event_q.with_entities(func.count(func.distinct(AnalyticsTrackingEvent.username))).scalar() or 0)
                latest_event_at = event_q.with_entities(func.max(AnalyticsTrackingEvent.event_time)).scalar()
                snapshot_q = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(
                    AnalyticsLearningBehaviorSnapshot.class_id == cls.id,
                    AnalyticsLearningBehaviorSnapshot.course_id == resolved_course_id,
                )
                snapshot_count = int(snapshot_q.count() or 0)
                latest_snapshot_at = snapshot_q.with_entities(func.max(AnalyticsLearningBehaviorSnapshot.calculated_at)).scalar()
                video_progress_count = int(self.db.query(AnalyticsStudentVideoProgress.id).filter(AnalyticsStudentVideoProgress.course_id == resolved_course_id).count() or 0)
                session_progress_count = int(self.db.query(AnalyticsStudentSessionProgress.id).filter(AnalyticsStudentSessionProgress.course_id == resolved_course_id).count() or 0)
                course_session_count = int(self.db.query(AnalyticsCourseSession.id).filter(AnalyticsCourseSession.course_id == resolved_course_id, AnalyticsCourseSession.active.is_(True)).count() or 0)
            else:
                mapped_ids = [str(cid) for cid in (mapping.get('mapped_course_ids') or []) if str(cid or '').strip()]
                unresolved_course_ids.update(mapped_ids)

            candidate_count = int(mapping.get('candidate_count') or 0)
            confidence_score = 0
            if mapping_status == 'resolved':
                confidence_score = max([int(item.get('score') or 0) for item in (mapping.get('candidates') or [])] or [70])
            elif mapping_status == 'ambiguous':
                confidence_score = 45
            elif mapping_status == 'missing':
                confidence_score = 0

            reasons: list[str] = []
            recommended_action = 'Không cần thao tác; mapping đủ rõ để orchestrator/recalculate xử lý.'
            reliability_status = 'READY'
            if roster_count <= 0:
                reliability_status = 'NO_ROSTER'
                reasons.append('NO_ROSTER')
                recommended_action = 'Đồng bộ roster AP/CMS cho lớp trước khi kiểm tra analytics.'
            elif mapping_status == 'missing':
                reliability_status = 'NO_COURSE_MAPPING'
                reasons.append('NO_COURSE_MAPPING')
                recommended_action = 'Ghép Course CMS/Open edX cho lớp hoặc môn/kỳ/cơ sở trước khi tính học online.'
            elif mapping_status == 'ambiguous':
                reliability_status = 'AMBIGUOUS_MAPPING'
                reasons.append('AMBIGUOUS_COURSE_MAPPING')
                recommended_action = 'Tạo class override mapping; hệ thống không tự chọn khi có nhiều course cùng độ khớp.'
            elif event_count <= 0 and video_progress_count <= 0 and session_progress_count <= 0:
                reliability_status = 'MAPPED_NO_EVENTS'
                reasons.append('MAPPED_NO_TRACKING_EVENTS')
                recommended_action = 'Kiểm tra Course ID, enrollment hoặc chờ ingest tracking.log có event mới.'
            elif snapshot_count <= 0:
                reliability_status = 'MAPPED_HAS_ACTIVITY_NO_SNAPSHOT'
                reasons.append('HAS_ACTIVITY_NO_SNAPSHOT')
                recommended_action = 'Để post-ingest orchestrator tính dần hoặc dùng doctor lớp để enqueue recalculate.'
            elif snapshot_count < roster_count:
                reliability_status = 'PARTIAL_SNAPSHOT'
                reasons.append('PARTIAL_SNAPSHOT')
                recommended_action = 'Tính lại lớp hoặc chờ orchestrator xử lý dần; UI vẫn hiển thị Chưa đủ dữ liệu cho sinh viên thiếu snapshot.'

            counters[reliability_status] += 1
            rows.append({
                'class_id': cls.id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'term_id': cls.term_id,
                'term_name': getattr(term, 'term_name', None),
                'subject_id': cls.subject_id,
                'subject_code': getattr(subject, 'subject_code', None),
                'subject_name': getattr(subject, 'subject_name', None),
                'mapping_status': mapping_status,
                'reliability_status': reliability_status,
                'resolved_course_id': resolved_course_id or None,
                'mapping_source': mapping.get('mapping_source'),
                'candidate_count': candidate_count,
                'confidence_score': min(100, max(0, confidence_score)),
                'roster_count': roster_count,
                'tracking_event_count': event_count,
                'tracking_user_count': event_user_count,
                'latest_tracking_event_at': self._iso_or_none(latest_event_at),
                'course_session_count': course_session_count,
                'video_progress_count': video_progress_count,
                'session_progress_count': session_progress_count,
                'snapshot_count': snapshot_count,
                'latest_snapshot_at': self._iso_or_none(latest_snapshot_at),
                'missing_snapshot_count': max(0, roster_count - snapshot_count),
                'reasons': reasons,
                'recommended_action': recommended_action,
                'mapping': mapping,
            })

        # Courses that have normalized tracking events but do not resolve to any
        # class under current mappings. This is often the real cause of 0/N class
        # result pages after ingest. Keep it bounded and read-only.
        event_course_rows = (
            self.db.query(
                AnalyticsTrackingEvent.course_id,
                func.count(AnalyticsTrackingEvent.id),
                func.count(func.distinct(AnalyticsTrackingEvent.username)),
                func.max(AnalyticsTrackingEvent.event_time),
            )
            .filter(AnalyticsTrackingEvent.course_id.isnot(None))
            .group_by(AnalyticsTrackingEvent.course_id)
            .order_by(func.max(AnalyticsTrackingEvent.event_time).desc().nullslast())
            .limit(100)
            .all()
        )
        courses_without_class_mapping: list[dict[str, Any]] = []
        for cid, event_total, user_total, latest_at in event_course_rows:
            clean = str(cid or '').strip()
            if not clean or (clean_course_id and clean != clean_course_id):
                continue
            resolved = self._resolve_recalculate_class_ids_for_courses(course_ids={clean}).get(clean, set())
            if allowed_class_ids is not None:
                resolved = {item for item in resolved if item in allowed_class_ids}
            if resolved:
                continue
            courses_without_class_mapping.append({
                'course_id': clean,
                'event_count': int(event_total or 0),
                'user_count': int(user_total or 0),
                'latest_event_at': self._iso_or_none(latest_at),
                'recommended_action': 'Tạo mapping Course CMS/Open edX về lớp/môn/kỳ phù hợp; không tự map nếu có nhiều lớp có thể khớp.',
            })
            if len(courses_without_class_mapping) >= 20:
                break

        blocker_count = int(counters.get('NO_ROSTER', 0) + counters.get('NO_COURSE_MAPPING', 0) + counters.get('AMBIGUOUS_MAPPING', 0) + len(courses_without_class_mapping))
        warning_count = int(counters.get('MAPPED_NO_EVENTS', 0) + counters.get('MAPPED_HAS_ACTIVITY_NO_SNAPSHOT', 0) + counters.get('PARTIAL_SNAPSHOT', 0))
        if blocker_count > 0:
            status = 'BLOCKED'
            summary_label = 'Chưa đủ tin cậy để tính/mở rộng analytics theo scope này'
        elif warning_count > 0:
            status = 'READY_WITH_WARNINGS'
            summary_label = 'Mapping đủ rõ, còn cảnh báo dữ liệu/snapshot'
        else:
            status = 'READY'
            summary_label = 'Mapping course/lớp đủ tin cậy cho scope đã chọn'

        next_actions: list[str] = []
        if counters.get('NO_COURSE_MAPPING'):
            next_actions.append('Ghép Course CMS/Open edX cho các lớp đang thiếu mapping.')
        if counters.get('AMBIGUOUS_MAPPING'):
            next_actions.append('Tạo class override mapping cho các lớp ambiguous; không để hệ thống tự chọn bừa.')
        if courses_without_class_mapping:
            next_actions.append('Xử lý các course có tracking event nhưng chưa resolve được class.')
        if counters.get('MAPPED_HAS_ACTIVITY_NO_SNAPSHOT') or counters.get('PARTIAL_SNAPSHOT'):
            next_actions.append('Cho post-ingest orchestrator chạy hoặc enqueue recalculate từng lớp qua doctor.')
        if not next_actions:
            next_actions.append('Có thể tiếp tục pilot analytics theo scope này; vẫn theo dõi SLA và readiness.')

        return {
            'version': getattr(settings, 'app_version', '25.9.16.7.2.64.12'),
            'report_type': 'analytics_course_class_mapping_reliability',
            'status': status,
            'summary_label': summary_label,
            'generated_at': datetime.utcnow().isoformat(),
            'filters': {
                'campus': clean_campus or None,
                'branch': clean_branch or None,
                'term_id': clean_term_id or None,
                'subject_id': clean_subject_id or None,
                'class_id': clean_class_id or None,
                'course_id': clean_course_id or None,
                'limit': safe_limit,
            },
            'dry_run': True,
            'read_only': True,
            'mutation_performed': False,
            'total_scope_classes': total_scope_classes,
            'returned_classes': len(rows),
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'counts': {key: int(value) for key, value in counters.items()},
            'resolved_course_count': len(resolved_course_ids),
            'courses_with_events_without_class_mapping_count': len(courses_without_class_mapping),
            'courses_with_events_without_class_mapping': courses_without_class_mapping,
            'items': rows,
            'next_actions': next_actions,
            'safe_policy': 'signals_only_not_violation',
            'read_only_guarantees': [
                'Không tạo/sửa/xóa course mapping.',
                'Không enqueue job và không recalculate trong request.',
                'Không đọc raw tracking.log; chỉ dùng bảng đã materialize.',
            ],
            'disclaimer': 'Báo cáo này kiểm tra độ tin cậy mapping course/lớp cho analytics, không kết luận hành vi cá nhân.',
        }

    def class_result_doctor(self, *, class_id: str, course_id: str | None = None) -> dict[str, Any]:
        """Operational doctor for the 0/N analytics result problem.

        The result page needs to distinguish an empty class from a class whose AP
        roster exists but analytics snapshots have not been produced yet. This
        method reads DB aggregates only; it never scans tracking.log directly.
        """
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            return {
                'status': 'blocked',
                'data_gap': 'CLASS_NOT_FOUND',
                'class_id': class_id,
                'message': 'Không tìm thấy lớp trong dữ liệu AP/CMS.',
                'recommended_action': 'Đồng bộ lại AP/CMS trước khi kiểm tra học online.',
                'safe_policy': 'signals_only_not_violation',
            }

        subject = self.db.get(AcademicSubject, cls.subject_id) if getattr(cls, 'subject_id', None) else None
        term = self.db.get(AcademicTerm, cls.term_id) if getattr(cls, 'term_id', None) else None
        roster = self._class_student_roster(class_id)
        roster_usernames = [str(item.get('username') or '').strip() for item in roster if str(item.get('username') or '').strip()]
        mapping = self._class_course_mapping_diagnostics(class_id=class_id, preferred_course_id=course_id)
        resolved_course_id = mapping.get('resolved_course_id') or course_id

        snapshot_q = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if resolved_course_id:
            snapshot_q = snapshot_q.filter(AnalyticsLearningBehaviorSnapshot.course_id == resolved_course_id)
        snapshot_count = int(snapshot_q.count() or 0)
        latest_snapshot = snapshot_q.order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first()

        tracking_event_count = 0
        tracking_user_count = 0
        latest_tracking_event_at = None
        video_progress_count = 0
        session_progress_count = 0
        video_user_count = 0
        session_user_count = 0
        session_structure_count = 0
        if resolved_course_id:
            event_q = self.db.query(AnalyticsTrackingEvent).filter(AnalyticsTrackingEvent.course_id == resolved_course_id)
            if roster_usernames:
                event_q = event_q.filter(AnalyticsTrackingEvent.username.in_(roster_usernames))
            tracking_event_count = int(event_q.count() or 0)
            tracking_user_count = int(event_q.with_entities(func.count(func.distinct(AnalyticsTrackingEvent.username))).scalar() or 0)
            latest_tracking_event_at = event_q.with_entities(func.max(AnalyticsTrackingEvent.event_time)).scalar()

            video_q = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.course_id == resolved_course_id)
            session_q = self.db.query(AnalyticsStudentSessionProgress).filter(AnalyticsStudentSessionProgress.course_id == resolved_course_id)
            if roster_usernames:
                video_q = video_q.filter(AnalyticsStudentVideoProgress.username.in_(roster_usernames))
                session_q = session_q.filter(AnalyticsStudentSessionProgress.username.in_(roster_usernames))
            video_progress_count = int(video_q.count() or 0)
            session_progress_count = int(session_q.count() or 0)
            video_user_count = int(video_q.with_entities(func.count(func.distinct(AnalyticsStudentVideoProgress.username))).scalar() or 0)
            session_user_count = int(session_q.with_entities(func.count(func.distinct(AnalyticsStudentSessionProgress.username))).scalar() or 0)
            session_structure_count = int(self.db.query(AnalyticsCourseSession.id).filter(AnalyticsCourseSession.course_id == resolved_course_id, AnalyticsCourseSession.active.is_(True)).count() or 0)

        latest_job = self.db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.class_id == class_id,
            AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
        ).order_by(AcademicClassSyncJob.created_at.desc()).first()
        active_job = self.db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.class_id == class_id,
            AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        ).order_by(AcademicClassSyncJob.created_at.desc()).first()
        guard = self.analytics_enqueue_guard(class_id=class_id)
        can_enqueue = bool(resolved_course_id and mapping.get('status') != 'ambiguous' and guard.get('allowed') and not active_job)

        roster_count = len(roster)
        missing_snapshot_count = max(0, roster_count - snapshot_count)
        if roster_count <= 0:
            data_gap = 'NO_ROSTER'
            status = 'blocked'
            message = 'Lớp chưa có roster sinh viên AP trong hệ thống.'
            recommended_action = 'Đồng bộ AP/CMS roster lớp trước khi tính học online.'
        elif mapping.get('status') == 'missing':
            data_gap = 'NO_COURSE_MAPPING'
            status = 'blocked'
            message = 'Lớp có roster AP nhưng chưa map Course CMS/Open edX.'
            recommended_action = 'Ghép Course CMS cho lớp/môn, sau đó để hệ thống tự tính lại.'
        elif mapping.get('status') == 'ambiguous':
            data_gap = 'AMBIGUOUS_COURSE_MAPPING'
            status = 'blocked'
            message = 'Lớp có nhiều Course CMS có thể khớp; cần chọn mapping rõ ràng.'
            recommended_action = 'Tạo class override mapping để tránh tính sai lớp.'
        elif tracking_event_count <= 0 and video_progress_count <= 0 and session_progress_count <= 0:
            data_gap = 'NO_TRACKING_EVENTS'
            status = 'waiting'
            message = 'Lớp đã có roster và Course CMS nhưng chưa thấy event học online đã ingest cho roster này.'
            recommended_action = 'Kiểm tra ingest tracking.log, enrollment/Course ID hoặc chờ event mới.'
        elif snapshot_count <= 0:
            data_gap = 'HAS_ACTIVITY_NO_SNAPSHOT'
            status = 'needs_recalculate'
            message = 'Đã có tín hiệu học nhưng chưa có snapshot nhận định.'
            recommended_action = 'Đưa tác vụ tính lại lớp vào worker; không cần tính toàn kỳ.'
        elif missing_snapshot_count > 0:
            data_gap = 'PARTIAL_SNAPSHOT'
            status = 'partial'
            message = 'Một phần sinh viên chưa có snapshot nhận định.'
            recommended_action = 'Tính lại lớp hoặc chờ post-ingest orchestrator xử lý dần.'
        else:
            data_gap = 'READY'
            status = 'ready'
            message = 'Dữ liệu lớp đã đủ để xem dashboard học online.'
            recommended_action = 'Có thể dùng kết quả như tín hiệu mềm và tiếp tục theo dõi job ingest.'

        return {
            'status': status,
            'data_gap': data_gap,
            'message': message,
            'recommended_action': recommended_action,
            'class': {
                'class_id': class_id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'term_id': cls.term_id,
                'term_name': term.term_name if term else None,
                'subject_id': cls.subject_id,
                'subject_code': subject.subject_code if subject else None,
            },
            'course_mapping': mapping,
            'resolved_course_id': resolved_course_id,
            'roster_count': roster_count,
            'snapshot_count': snapshot_count,
            'missing_snapshot_count': missing_snapshot_count,
            'tracking_event_count': tracking_event_count,
            'tracking_user_count': tracking_user_count,
            'latest_tracking_event_at': self._iso_or_none(latest_tracking_event_at),
            'video_progress_count': video_progress_count,
            'video_user_count': video_user_count,
            'session_progress_count': session_progress_count,
            'session_user_count': session_user_count,
            'session_structure_count': session_structure_count,
            'latest_behavior_calculated_at': self._iso_or_none(latest_snapshot.calculated_at if latest_snapshot else None),
            'last_recalculate_job': ({
                'id': latest_job.id,
                'status': latest_job.status,
                'created_at': self._iso_or_none(latest_job.created_at),
                'updated_at': self._iso_or_none(latest_job.updated_at),
                'progress_label': latest_job.progress_label,
            } if latest_job else None),
            'active_recalculate_job': ({
                'id': active_job.id,
                'status': active_job.status,
                'created_at': self._iso_or_none(active_job.created_at),
                'progress_label': active_job.progress_label,
            } if active_job else None),
            'recalculate': {
                'can_enqueue': can_enqueue,
                'course_id': resolved_course_id,
                'guard': guard,
                'disabled_reasons': ([] if can_enqueue else [
                    reason for reason in [
                        'NO_RESOLVED_COURSE' if not resolved_course_id else '',
                        'AMBIGUOUS_COURSE_MAPPING' if mapping.get('status') == 'ambiguous' else '',
                        'CLASS_JOB_ALREADY_ACTIVE' if active_job else '',
                    ] + list(guard.get('reasons') or []) if reason
                ]),
            },
            'safe_policy': 'signals_only_not_violation',
        }

    def behavior_summary(self, *, class_id: str | None, course_id: str | None = None) -> dict[str, Any]:
        q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if class_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if course_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)
        rows = q.all()
        counts = Counter(r.classification for r in rows)
        quality = Counter(r.data_quality for r in rows)

        roster = self._class_student_roster(class_id) if class_id else []
        snapshot_usernames = {self._normal_username(r.username) for r in rows if r.username}
        missing_roster_count = len([item for item in roster if self._normal_username(item.get('username')) not in snapshot_usernames])
        if missing_roster_count:
            counts['INSUFFICIENT_DATA'] += missing_roster_count
            quality['MISSING'] += missing_roster_count

        total_students = max(len(rows), len(roster)) if class_id else len(rows)
        if class_id and roster:
            data_status = 'ready' if len(rows) >= len(roster) else ('partial' if rows else 'not_calculated')
        else:
            data_status = 'ready' if rows else 'not_calculated'
        diagnostics = self.class_result_doctor(class_id=class_id, course_id=course_id) if class_id else None
        return {
            'total_students': total_students,
            'roster_count': len(roster),
            'snapshot_count': len(rows),
            'missing_snapshot_count': missing_roster_count,
            'data_status': data_status,
            'likely_real_learning_count': counts.get('LIKELY_REAL_LEARNING', 0),
            'possible_idle_count': counts.get('POSSIBLE_IDLE', 0),
            'possible_suspicious_count': counts.get('POSSIBLE_ANOMALY', 0) + counts.get('POSSIBLE_CHEATING', 0),
            'insufficient_data_count': counts.get('INSUFFICIENT_DATA', 0),
            'normal_count': counts.get('NORMAL', 0),
            'data_quality_breakdown': dict(quality),
            'diagnostics': diagnostics,
            'disclaimer': 'Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.',
        }

    def behavior_rows(self, *, class_id: str | None, course_id: str | None = None, classification: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if class_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if course_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)

        normalized_classification = str(classification or 'all').strip().upper()
        apply_snapshot_classification_filter = normalized_classification and normalized_classification != 'ALL'
        if apply_snapshot_classification_filter:
            if normalized_classification in {'POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING'}:
                q = q.filter(AnalyticsLearningBehaviorSnapshot.classification.in_(['POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING']))
            else:
                q = q.filter(AnalyticsLearningBehaviorSnapshot.classification == normalized_classification)

        snapshot_rows = q.order_by(
            AnalyticsLearningBehaviorSnapshot.suspicious_score.desc(),
            AnalyticsLearningBehaviorSnapshot.calculated_at.desc(),
        ).all()

        roster_identity = {self._normal_username(item.get('username')): item for item in (self._class_student_roster(class_id) if class_id else [])}

        def snapshot_item(r: AnalyticsLearningBehaviorSnapshot) -> dict[str, Any]:
            student_identity = roster_identity.get(self._normal_username(r.username)) or {}
            return {
                'username': r.username,
                'student_code': student_identity.get('student_code'),
                'full_name': student_identity.get('full_name'),
                'user_id': r.user_id,
                'course_id': r.course_id,
                'class_id': r.class_id,
                'classification': r.classification,
                'display_label': r.display_label,
                'confidence_score': r.confidence_score,
                'real_learning_score': r.real_learning_score,
                'idle_score': r.idle_score,
                'suspicious_score': r.suspicious_score,
                'deadline_compliance_percent': r.deadline_compliance_percent,
                'crammed_session_count': r.crammed_session_count,
                'quiz_before_video_count': r.quiz_before_video_count,
                'reason_codes': r.reason_codes or [],
                'human_readable_summary': r.human_readable_summary,
                'recommended_action': r.recommended_action,
                'data_quality': r.data_quality,
                'calculated_at': r.calculated_at.isoformat() if r.calculated_at else None,
                'last_activity_at': r.last_activity_at.isoformat() if r.last_activity_at else None,
            }

        items = [snapshot_item(r) for r in snapshot_rows]

        # Roster fallback: if behavior snapshots have not been materialized for
        # every AP student in the class, still show those students as
        # INSUFFICIENT_DATA instead of returning an empty/partial table. This is
        # intentionally conservative: the UI must distinguish "no snapshot yet"
        # from "class has no students".
        if class_id and normalized_classification in {'ALL', 'INSUFFICIENT_DATA'}:
            roster = self._class_student_roster(class_id)
            present_usernames = {self._normal_username(item.get('username')) for item in items}
            resolved_course = self._course_for_class(class_id, course_id) or course_id or ''
            activity_by_username: dict[str, dict[str, Any]] = {}
            if resolved_course and roster:
                roster_names = [item['username'] for item in roster if item.get('username')]
                if roster_names:
                    video_rows = self.db.query(
                        AnalyticsStudentVideoProgress.username,
                        func.max(AnalyticsStudentVideoProgress.last_event_at),
                        func.count(AnalyticsStudentVideoProgress.id),
                    ).filter(
                        AnalyticsStudentVideoProgress.course_id == resolved_course,
                        AnalyticsStudentVideoProgress.username.in_(roster_names),
                    ).group_by(AnalyticsStudentVideoProgress.username).all()
                    for username, last_at, count in video_rows:
                        key = self._normal_username(username)
                        activity_by_username.setdefault(key, {'has_activity': False, 'last_activity_at': None, 'activity_count': 0})
                        activity_by_username[key]['has_activity'] = True
                        activity_by_username[key]['last_activity_at'] = last_at
                        activity_by_username[key]['activity_count'] += int(count or 0)
                    session_rows = self.db.query(
                        AnalyticsStudentSessionProgress.username,
                        func.max(AnalyticsStudentSessionProgress.last_activity_at),
                        func.count(AnalyticsStudentSessionProgress.id),
                    ).filter(
                        AnalyticsStudentSessionProgress.course_id == resolved_course,
                        AnalyticsStudentSessionProgress.username.in_(roster_names),
                    ).group_by(AnalyticsStudentSessionProgress.username).all()
                    for username, last_at, count in session_rows:
                        key = self._normal_username(username)
                        current = activity_by_username.setdefault(key, {'has_activity': False, 'last_activity_at': None, 'activity_count': 0})
                        current['has_activity'] = True
                        if last_at and (not current.get('last_activity_at') or last_at > current.get('last_activity_at')):
                            current['last_activity_at'] = last_at
                        current['activity_count'] += int(count or 0)

            for student in roster:
                username = student.get('username')
                if not username or self._normal_username(username) in present_usernames:
                    continue
                activity = activity_by_username.get(self._normal_username(username)) or {}
                has_activity = bool(activity.get('has_activity'))
                items.append({
                    'username': username,
                    'user_id': None,
                    'course_id': resolved_course,
                    'class_id': class_id,
                    'classification': 'INSUFFICIENT_DATA',
                    'display_label': 'Chưa đủ dữ liệu',
                    'confidence_score': 25 if has_activity else 0,
                    'real_learning_score': 0,
                    'idle_score': 0,
                    'suspicious_score': 0,
                    'deadline_compliance_percent': None,
                    'crammed_session_count': 0,
                    'quiz_before_video_count': 0,
                    'reason_codes': ['NO_BEHAVIOR_SNAPSHOT'] + (['HAS_LEARNING_ACTIVITY'] if has_activity else []),
                    'human_readable_summary': 'Đã có tín hiệu học nhưng chưa có snapshot nhận định. Hãy chạy lại tính toán học online.' if has_activity else 'Sinh viên thuộc lớp AP nhưng chưa có snapshot nhận định học online.',
                    'recommended_action': 'Tính lại học online cho lớp' if has_activity else 'Chờ dữ liệu học hoặc chạy đồng bộ full CMS',
                    'data_quality': 'PARTIAL' if has_activity else 'MISSING',
                    'student_code': student.get('student_code'),
                    'full_name': student.get('full_name'),
                    'calculated_at': None,
                    'last_activity_at': activity.get('last_activity_at').isoformat() if activity.get('last_activity_at') else None,
                })

        total = len(items)
        safe_offset = max(0, int(offset or 0))
        safe_limit = min(max(1, int(limit or 100)), 200)
        diagnostics = self.class_result_doctor(class_id=class_id, course_id=course_id) if class_id else None
        return {
            'total': total,
            'items': items[safe_offset:safe_offset + safe_limit],
            'roster_fallback': class_id is not None,
            'diagnostics': diagnostics,
        }
