from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func

from app.core.config import settings
from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob
from app.models.learning_analytics import (
    AnalyticsCourseSession,
    AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentSessionProgress,
    AnalyticsStudentVideoProgress,
    AnalyticsTrackingEvent,
)


class LearningAnalyticsOperationsWorkflowService:
    """Read-only SLA, pilot-acceptance and UAT evidence workflow split.

    The class receives the parent core service and delegates low-level helpers
    back to it so behavior stays compatible while the public workflow is no
    longer hosted directly in analytics_core_service.py.
    """

    def __init__(self, parent: Any):
        self.parent = parent
        self.db = parent.db

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parent, name)

    def analytics_sla_report(
        self,
        *,
        allowed_class_ids: set[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Operational SLA dashboard for ingest -> recalculate -> snapshot.

        This endpoint is intentionally read-only and aggregate-only. It does not
        scan tracking.log, does not recalculate inside the request, and does not
        create jobs. It answers the production operator question: "Log vào rồi,
        worker đã tính chưa, lớp nào còn kẹt?".
        """
        now = datetime.utcnow()
        limit = max(1, min(int(limit or getattr(settings, 'analytics_sla_class_gap_limit', 20) or 20), 100))
        ingest_target_seconds = max(60, int(getattr(settings, 'analytics_sla_ingest_target_seconds', 300) or 300))
        snapshot_target_seconds = max(300, int(getattr(settings, 'analytics_sla_snapshot_target_seconds', 3600) or 3600))
        max_queued_jobs = max(1, int(getattr(settings, 'analytics_sla_max_queued_jobs', 50) or 50))
        max_failed_jobs_last_hour = max(0, int(getattr(settings, 'analytics_sla_max_failed_jobs_last_hour', 0) or 0))
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(hours=24)

        ingest = self.ingest_status()
        last_ingest_at = self._parse_datetime_filter(ingest.get('last_run_at'))
        seconds_since_ingest = max(0, int((now - last_ingest_at).total_seconds())) if last_ingest_at else None
        post_ingest = ((ingest.get('stats') or {}).get('post_ingest_recalculate') or {}) if isinstance(ingest.get('stats'), dict) else {}

        event_base = self.db.query(AnalyticsTrackingEvent)
        event_count_total = event_base.count()
        latest_event_at = event_base.with_entities(func.max(AnalyticsTrackingEvent.event_time)).scalar()
        latest_event_created_at = event_base.with_entities(func.max(AnalyticsTrackingEvent.created_at)).scalar()
        events_last_hour = event_base.filter(AnalyticsTrackingEvent.created_at >= one_hour_ago).count()
        distinct_course_last_hour = event_base.filter(AnalyticsTrackingEvent.created_at >= one_hour_ago, AnalyticsTrackingEvent.course_id.isnot(None)).with_entities(func.count(func.distinct(AnalyticsTrackingEvent.course_id))).scalar() or 0
        distinct_user_last_hour = event_base.filter(AnalyticsTrackingEvent.created_at >= one_hour_ago, AnalyticsTrackingEvent.username.isnot(None)).with_entities(func.count(func.distinct(AnalyticsTrackingEvent.username))).scalar() or 0

        job_q = self.db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.job_type == 'learning_analytics_recalculate')
        if allowed_class_ids is not None:
            job_q = job_q.filter(AcademicClassSyncJob.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else job_q.filter(False)
        job_rows = job_q.with_entities(AcademicClassSyncJob.status, func.count(AcademicClassSyncJob.id)).group_by(AcademicClassSyncJob.status).all()
        job_by_status = {str(status or 'unknown'): int(count or 0) for status, count in job_rows}
        queued_jobs = int(job_by_status.get('queued', 0))
        running_jobs = int(job_by_status.get('running', 0))
        active_jobs = queued_jobs + running_jobs
        completed_last_hour = job_q.filter(AcademicClassSyncJob.status == 'completed', AcademicClassSyncJob.finished_at >= one_hour_ago).count()
        failed_last_hour = job_q.filter(AcademicClassSyncJob.status == 'failed', AcademicClassSyncJob.finished_at >= one_hour_ago).count()
        completed_last_24h = job_q.filter(AcademicClassSyncJob.status == 'completed', AcademicClassSyncJob.finished_at >= one_day_ago).count()
        failed_last_24h = job_q.filter(AcademicClassSyncJob.status == 'failed', AcademicClassSyncJob.finished_at >= one_day_ago).count()
        latest_job = job_q.order_by(AcademicClassSyncJob.created_at.desc()).first()
        stuck_cutoff = now - timedelta(minutes=max(5, int(getattr(settings, 'analytics_monitoring_stuck_job_minutes', 60) or 60)))
        stuck_jobs = (
            job_q.filter(AcademicClassSyncJob.status.in_(['queued', 'running']), AcademicClassSyncJob.created_at < stuck_cutoff)
            .order_by(AcademicClassSyncJob.created_at.asc())
            .limit(10)
            .all()
        )

        snapshot_q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if allowed_class_ids is not None:
            snapshot_q = snapshot_q.filter(AnalyticsLearningBehaviorSnapshot.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else snapshot_q.filter(False)
        snapshot_count = snapshot_q.count()
        latest_snapshot_at = snapshot_q.with_entities(func.max(AnalyticsLearningBehaviorSnapshot.calculated_at)).scalar()
        seconds_since_latest_snapshot = max(0, int((now - latest_snapshot_at).total_seconds())) if latest_snapshot_at else None
        snapshots_last_hour = snapshot_q.filter(AnalyticsLearningBehaviorSnapshot.calculated_at >= one_hour_ago).count()
        snapshot_student_count = snapshot_q.with_entities(func.count(func.distinct(AnalyticsLearningBehaviorSnapshot.username))).scalar() or 0
        snapshot_class_count = snapshot_q.with_entities(func.count(func.distinct(AnalyticsLearningBehaviorSnapshot.class_id))).scalar() or 0

        roster_rows_q = (
            self.db.query(
                AcademicClass.id.label('class_id'),
                AcademicClass.class_code.label('class_code'),
                AcademicClass.campus.label('campus'),
                AcademicClass.branch.label('branch'),
                AcademicClassCourseMapping.openedx_course_id.label('course_id'),
                func.count(func.distinct(AcademicClassStudent.student_id)).label('student_count'),
                func.count(func.distinct(AnalyticsLearningBehaviorSnapshot.username)).label('snapshot_count'),
                func.max(AnalyticsLearningBehaviorSnapshot.calculated_at).label('latest_snapshot_at'),
            )
            .join(AcademicClassStudent, AcademicClassStudent.class_id == AcademicClass.id)
            .outerjoin(AcademicClassCourseMapping, and_(AcademicClassCourseMapping.class_id == AcademicClass.id, AcademicClassCourseMapping.active.is_(True)))
            .outerjoin(AnalyticsLearningBehaviorSnapshot, AnalyticsLearningBehaviorSnapshot.class_id == AcademicClass.id)
            .filter(AcademicClass.active.is_(True))
            .group_by(AcademicClass.id, AcademicClass.class_code, AcademicClass.campus, AcademicClass.branch, AcademicClassCourseMapping.openedx_course_id)
        )
        if allowed_class_ids is not None:
            roster_rows_q = roster_rows_q.filter(AcademicClass.id.in_(sorted(allowed_class_ids))) if allowed_class_ids else roster_rows_q.filter(False)
        roster_rows = roster_rows_q.all()
        class_gap_items: list[dict[str, Any]] = []
        roster_class_count = 0
        roster_student_count = 0
        for row in roster_rows:
            student_count = int(row.student_count or 0)
            snapshot_row_count = int(row.snapshot_count or 0)
            roster_class_count += 1
            roster_student_count += student_count
            latest_row_snapshot = row.latest_snapshot_at
            row_age_seconds = max(0, int((now - latest_row_snapshot).total_seconds())) if latest_row_snapshot else None
            missing_count = max(0, student_count - snapshot_row_count)
            stale = row_age_seconds is not None and row_age_seconds > snapshot_target_seconds
            if missing_count > 0 or stale:
                class_gap_items.append({
                    'class_id': str(row.class_id),
                    'class_code': row.class_code,
                    'campus': row.campus,
                    'branch': row.branch,
                    'course_id': row.course_id,
                    'student_count': student_count,
                    'snapshot_count': snapshot_row_count,
                    'missing_snapshot_count': missing_count,
                    'latest_snapshot_at': latest_row_snapshot.isoformat() if latest_row_snapshot else None,
                    'snapshot_age_seconds': row_age_seconds,
                    'gap_status': 'NO_SNAPSHOT' if snapshot_row_count <= 0 else ('STALE_SNAPSHOT' if stale else 'PARTIAL_SNAPSHOT'),
                })
        class_gap_items.sort(key=lambda item: (item.get('gap_status') != 'NO_SNAPSHOT', -(int(item.get('missing_snapshot_count') or 0)), item.get('class_code') or ''))

        issues: list[dict[str, Any]] = []
        if not ingest.get('file_exists'):
            issues.append({'severity': 'BLOCKER', 'code': 'TRACKING_LOG_NOT_MOUNTED', 'category': 'Ingest', 'message': 'AI Server chưa thấy tracking.log Open edX.', 'action': 'Kiểm tra mount log trong backend/worker/beat.'})
        if not ingest.get('enabled'):
            issues.append({'severity': 'BLOCKER', 'code': 'INGEST_DISABLED', 'category': 'Ingest', 'message': 'Analytics ingest đang tắt.', 'action': 'Bật ANALYTICS_INGEST_ENABLED=true.'})
        if seconds_since_ingest is None:
            issues.append({'severity': 'WARNING', 'code': 'INGEST_NEVER_RAN', 'category': 'Ingest', 'message': 'Chưa có lượt ingest nào chạy.', 'action': 'Chờ beat hoặc enqueue ingest job thủ công.'})
        elif seconds_since_ingest > ingest_target_seconds:
            issues.append({'severity': 'WARNING', 'code': 'INGEST_SLA_LATE', 'category': 'Ingest', 'message': 'Ingest tracking log đã trễ so với SLA.', 'action': 'Kiểm tra beat/worker và /jobs.', 'details': {'seconds_since_ingest': seconds_since_ingest, 'target_seconds': ingest_target_seconds}})
        if failed_last_hour > max_failed_jobs_last_hour:
            issues.append({'severity': 'WARNING', 'code': 'RECALCULATE_JOB_FAILURES', 'category': 'Worker jobs', 'message': 'Có job tính lại analytics lỗi trong 1 giờ gần nhất.', 'action': 'Mở /jobs lọc learning_analytics_recalculate để xem lỗi.', 'details': {'failed_last_hour': int(failed_last_hour)}})
        if queued_jobs > max_queued_jobs:
            issues.append({'severity': 'WARNING', 'code': 'RECALCULATE_QUEUE_BACKLOG', 'category': 'Worker jobs', 'message': 'Hàng đợi tính lại analytics đang cao.', 'action': 'Chờ worker xử lý hoặc tăng worker có kiểm soát.', 'details': {'queued_jobs': queued_jobs, 'max_queued_jobs': max_queued_jobs}})
        if stuck_jobs:
            issues.append({'severity': 'WARNING', 'code': 'STUCK_RECALCULATE_JOBS', 'category': 'Worker jobs', 'message': 'Có job analytics queued/running quá lâu.', 'action': 'Kiểm tra worker logs và restart worker nếu job treo thật.', 'details': {'stuck_job_count': len(stuck_jobs)}})
        if event_count_total > 0 and snapshot_count <= 0:
            issues.append({'severity': 'WARNING', 'code': 'EVENTS_WITHOUT_SNAPSHOTS', 'category': 'Snapshot', 'message': 'Đã có tracking events nhưng chưa có snapshot nhận định.', 'action': 'Kiểm tra post-ingest orchestrator hoặc bấm Tính lại lớp trong doctor.'})
        if class_gap_items:
            issues.append({'severity': 'INFO', 'code': 'CLASSES_NEED_SNAPSHOT', 'category': 'Snapshot', 'message': 'Một số lớp có roster AP nhưng thiếu hoặc stale snapshot.', 'action': 'Ưu tiên tính lại các lớp trong danh sách SLA gap.'})

        sections = [
            {
                'key': 'ingest',
                'title': 'Ingest tracking.log',
                'status': 'OK' if ingest.get('file_exists') and ingest.get('enabled') and (seconds_since_ingest is not None and seconds_since_ingest <= ingest_target_seconds) else ('BLOCKED' if not ingest.get('file_exists') or not ingest.get('enabled') else 'WARNING'),
                'target_seconds': ingest_target_seconds,
                'actual_seconds': seconds_since_ingest,
                'metrics': {
                    'last_run_at': ingest.get('last_run_at'),
                    'last_status': ingest.get('last_status'),
                    'total_events_inserted': int(ingest.get('total_events_inserted') or 0),
                    'events_last_hour': int(events_last_hour or 0),
                    'distinct_courses_last_hour': int(distinct_course_last_hour or 0),
                    'distinct_users_last_hour': int(distinct_user_last_hour or 0),
                },
            },
            {
                'key': 'orchestrator',
                'title': 'Post-ingest orchestrator',
                'status': 'OK' if bool(getattr(settings, 'analytics_post_ingest_recalculate_enabled', True)) else 'WARNING',
                'metrics': {
                    'enabled': bool(getattr(settings, 'analytics_post_ingest_recalculate_enabled', True)),
                    'cooldown_seconds': int(getattr(settings, 'analytics_post_ingest_recalculate_cooldown_seconds', 900) or 900),
                    'max_jobs_per_run': int(getattr(settings, 'analytics_post_ingest_recalculate_max_jobs_per_run', 10) or 10),
                    'last_post_ingest': post_ingest,
                },
            },
            {
                'key': 'jobs',
                'title': 'Worker recalculate jobs',
                'status': 'WARNING' if failed_last_hour > max_failed_jobs_last_hour or queued_jobs > max_queued_jobs or stuck_jobs else 'OK',
                'metrics': {
                    'by_status': job_by_status,
                    'active_jobs': active_jobs,
                    'completed_last_hour': int(completed_last_hour or 0),
                    'failed_last_hour': int(failed_last_hour or 0),
                    'completed_last_24h': int(completed_last_24h or 0),
                    'failed_last_24h': int(failed_last_24h or 0),
                    'latest_job': {
                        'id': latest_job.id,
                        'status': latest_job.status,
                        'class_id': latest_job.class_id,
                        'created_at': latest_job.created_at.isoformat() if latest_job.created_at else None,
                        'finished_at': latest_job.finished_at.isoformat() if latest_job.finished_at else None,
                        'progress_label': latest_job.progress_label,
                    } if latest_job else None,
                    'stuck_jobs': [
                        {'id': job.id, 'class_id': job.class_id, 'status': job.status, 'created_at': job.created_at.isoformat() if job.created_at else None, 'progress_label': job.progress_label}
                        for job in stuck_jobs
                    ],
                },
            },
            {
                'key': 'snapshots',
                'title': 'Behavior snapshots',
                'status': 'WARNING' if (snapshot_count <= 0 and event_count_total > 0) else 'OK',
                'target_seconds': snapshot_target_seconds,
                'actual_seconds': seconds_since_latest_snapshot,
                'metrics': {
                    'snapshot_count': int(snapshot_count or 0),
                    'snapshot_student_count': int(snapshot_student_count or 0),
                    'snapshot_class_count': int(snapshot_class_count or 0),
                    'snapshots_last_hour': int(snapshots_last_hour or 0),
                    'latest_snapshot_at': latest_snapshot_at.isoformat() if latest_snapshot_at else None,
                    'classes_with_roster': roster_class_count,
                    'roster_student_count': roster_student_count,
                    'class_gap_count': len(class_gap_items),
                },
            },
        ]
        status_value = self._sla_status(issues)
        next_actions = []
        seen_actions: set[str] = set()
        for issue in issues:
            action = str(issue.get('action') or '').strip()
            if action and action not in seen_actions:
                seen_actions.add(action)
                next_actions.append(action)
        return {
            'version': getattr(settings, 'app_version', '25.9.16.7.2.64.12'),
            'sla_status': status_value,
            'summary_label': 'SLA ổn định' if status_value == 'OK' else ('SLA bị chặn' if status_value == 'BLOCKED' else 'SLA cần theo dõi'),
            'generated_at': now.isoformat(),
            'targets': {
                'ingest_target_seconds': ingest_target_seconds,
                'snapshot_target_seconds': snapshot_target_seconds,
                'max_queued_jobs': max_queued_jobs,
                'max_failed_jobs_last_hour': max_failed_jobs_last_hour,
            },
            'counters': {
                'tracking_event_count': int(event_count_total or 0),
                'events_last_hour': int(events_last_hour or 0),
                'distinct_courses_last_hour': int(distinct_course_last_hour or 0),
                'distinct_users_last_hour': int(distinct_user_last_hour or 0),
                'recalculate_active_jobs': active_jobs,
                'recalculate_completed_last_hour': int(completed_last_hour or 0),
                'recalculate_failed_last_hour': int(failed_last_hour or 0),
                'behavior_snapshot_count': int(snapshot_count or 0),
                'snapshots_last_hour': int(snapshots_last_hour or 0),
                'classes_with_roster_gap': len(class_gap_items),
            },
            'latency': {
                'seconds_since_last_ingest': seconds_since_ingest,
                'seconds_since_latest_event': max(0, int((now - latest_event_created_at).total_seconds())) if latest_event_created_at else None,
                'seconds_since_latest_snapshot': seconds_since_latest_snapshot,
            },
            'ingest': ingest,
            'post_ingest_recalculate': post_ingest,
            'sections': sections,
            'issues': issues,
            'next_actions': next_actions,
            'classes_needing_snapshot': class_gap_items[:limit],
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'SLA chỉ đo độ trễ vận hành ingest/recalculate/snapshot; không kết luận hành vi cá nhân.',
        }

    def pilot_acceptance_report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        sample_limit: int = 5,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Production pilot gate for 1-3 real classes.

        This report is deliberately metadata/snapshot based. It never scans
        tracking.log and never recalculates behavior during the request. It is
        intended for the final human acceptance step before enabling analytics
        broadly: verify mount -> ingest -> session mapping -> backfill -> sample
        evidence -> safe wording.
        """
        sample_limit = max(1, min(int(sample_limit or 5), 20))
        production = self.production_readiness_report(allowed_class_ids=allowed_class_ids)
        data_quality = self.analytics_data_quality_report(class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids)
        backfill = self.analytics_backfill_plan(campus=campus, branch=branch, class_id=class_id, course_id=course_id, limit=10, allowed_class_ids=allowed_class_ids)

        resolved_course_id = self._course_for_class(class_id, course_id)
        classes_q = self.db.query(AcademicClass)
        if allowed_class_ids is not None:
            classes_q = classes_q.filter(AcademicClass.id.in_(sorted(allowed_class_ids))) if allowed_class_ids else classes_q.filter(False)
        if class_id:
            classes_q = classes_q.filter(AcademicClass.id == class_id)
        if campus:
            classes_q = classes_q.filter(func.lower(AcademicClass.campus) == campus.lower())
        if branch:
            classes_q = classes_q.filter(func.lower(AcademicClass.branch) == branch.lower())
        pilot_classes = classes_q.order_by(AcademicClass.updated_at.desc()).limit(3).all()

        class_items: list[dict[str, Any]] = []
        blocker_codes: list[str] = []
        warning_codes: list[str] = []
        total_students = 0
        total_snapshots = 0
        total_session_snapshots = 0
        total_video_snapshots = 0

        for cls in pilot_classes:
            cid = str(cls.id)
            c_course = self._course_for_class(cid, resolved_course_id)
            student_count = self.db.query(AcademicClassStudent.id).filter(AcademicClassStudent.class_id == cid).count()
            behavior_q = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(AnalyticsLearningBehaviorSnapshot.class_id == cid)
            if c_course:
                behavior_q = behavior_q.filter(AnalyticsLearningBehaviorSnapshot.course_id == c_course)
            behavior_count = behavior_q.count()
            latest_behavior = behavior_q.order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first()
            sessions = self.db.query(AnalyticsCourseSession.id).filter(
                AnalyticsCourseSession.course_id == c_course,
                AnalyticsCourseSession.active.is_(True),
            ).count() if c_course else 0
            session_snapshots = self.db.query(AnalyticsStudentSessionProgress.id).filter(
                AnalyticsStudentSessionProgress.course_id == c_course,
            ).count() if c_course else 0
            video_snapshots = self.db.query(AnalyticsStudentVideoProgress.id).filter(
                AnalyticsStudentVideoProgress.course_id == c_course,
            ).count() if c_course else 0
            classifications = dict(behavior_q.with_entities(AnalyticsLearningBehaviorSnapshot.classification, func.count(AnalyticsLearningBehaviorSnapshot.id)).group_by(AnalyticsLearningBehaviorSnapshot.classification).all()) if behavior_count else {}
            data_quality_breakdown = dict(behavior_q.with_entities(AnalyticsLearningBehaviorSnapshot.data_quality, func.count(AnalyticsLearningBehaviorSnapshot.id)).group_by(AnalyticsLearningBehaviorSnapshot.data_quality).all()) if behavior_count else {}

            reasons: list[str] = []
            status = 'PASS'
            if not c_course:
                status = 'FAIL'
                reasons.append('MISSING_COURSE_MAPPING')
            if student_count <= 0:
                status = 'FAIL'
                reasons.append('NO_STUDENTS')
            if sessions <= 0:
                status = 'FAIL'
                reasons.append('MISSING_SESSION_STRUCTURE')
            if behavior_count <= 0:
                status = 'FAIL'
                reasons.append('NO_BEHAVIOR_SNAPSHOT')
            elif student_count and behavior_count < max(1, int(student_count * 0.5)):
                status = 'WARN' if status == 'PASS' else status
                reasons.append('LOW_BEHAVIOR_COVERAGE')
            if video_snapshots <= 0:
                status = 'WARN' if status == 'PASS' else status
                reasons.append('NO_VIDEO_PROGRESS_SNAPSHOT')
            if (classifications.get('POSSIBLE_ANOMALY', 0) or classifications.get('POSSIBLE_CHEATING', 0)):
                reasons.append('HAS_ATTENTION_SIGNALS_REQUIRING_TEACHER_REVIEW')

            if status == 'FAIL':
                blocker_codes.extend(reasons)
            elif status == 'WARN':
                warning_codes.extend(reasons)

            total_students += int(student_count or 0)
            total_snapshots += int(behavior_count or 0)
            total_session_snapshots += int(session_snapshots or 0)
            total_video_snapshots += int(video_snapshots or 0)
            class_items.append({
                'class_id': cid,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'course_id': c_course,
                'student_count': int(student_count or 0),
                'behavior_snapshot_count': int(behavior_count or 0),
                'session_count': int(sessions or 0),
                'session_progress_count': int(session_snapshots or 0),
                'video_progress_count': int(video_snapshots or 0),
                'classification_breakdown': {str(k or 'UNKNOWN'): int(v or 0) for k, v in classifications.items()},
                'data_quality_breakdown': {str(k or 'UNKNOWN'): int(v or 0) for k, v in data_quality_breakdown.items()},
                'latest_behavior_calculated_at': latest_behavior.calculated_at.isoformat() if latest_behavior and latest_behavior.calculated_at else None,
                'acceptance_status': status,
                'reasons': reasons,
                'recommended_action': 'Có thể pilot lớp này.' if status == 'PASS' else ('Backfill/tính lại học online và kiểm tra mapping trước.' if status == 'FAIL' else 'Có thể pilot hẹp nhưng cần kiểm tra cảnh báo.'),
            })

        sample_q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if allowed_class_ids is not None:
            sample_q = sample_q.filter(AnalyticsLearningBehaviorSnapshot.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else sample_q.filter(False)
        if class_id:
            sample_q = sample_q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if resolved_course_id:
            sample_q = sample_q.filter(AnalyticsLearningBehaviorSnapshot.course_id == resolved_course_id)
        sample_rows = sample_q.order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).limit(sample_limit).all()
        samples = [
            {
                'class_id': row.class_id,
                'course_id': row.course_id,
                'username': row.username,
                'classification': row.classification,
                'display_label': self._safe_label(row.classification, row.display_label),
                'confidence_score': row.confidence_score,
                'real_learning_score': row.real_learning_score,
                'idle_score': row.idle_score,
                'suspicious_score': row.suspicious_score,
                'reason_codes': row.reason_codes or [],
                'summary': row.human_readable_summary,
                'recommended_action': self._recommended_action_label(row.recommended_action),
                'data_quality': row.data_quality,
                'calculated_at': row.calculated_at.isoformat() if row.calculated_at else None,
            }
            for row in sample_rows
        ]

        ingest = self.ingest_status()
        global_blockers = [i.get('code') for i in production.get('issues') or [] if str(i.get('severity')).upper() == 'BLOCKER']
        blocker_codes.extend([str(c) for c in global_blockers if c])
        blocker_codes = sorted(set(blocker_codes))
        warning_codes = sorted(set(warning_codes + [str(i.get('code')) for i in production.get('issues') or [] if str(i.get('severity')).upper() == 'WARNING' and i.get('code')]))
        pilot_status = 'PASS' if not blocker_codes and class_items and total_snapshots > 0 else 'FAIL'
        if pilot_status == 'PASS' and warning_codes:
            pilot_status = 'PASS_WITH_WARNINGS'

        checklist = [
            {'key': 'tracking_log_mounted', 'label': 'tracking.log đã mount read-only', 'passed': bool(ingest.get('file_exists'))},
            {'key': 'ingest_has_events', 'label': 'Đã ingest tracking events', 'passed': int(ingest.get('total_events_inserted') or 0) > 0},
            {'key': 'pilot_classes_found', 'label': 'Có lớp trong phạm vi pilot', 'passed': bool(class_items)},
            {'key': 'session_structure_ready', 'label': 'Có mapping Bài/Session → video → quiz', 'passed': all((i.get('session_count') or 0) > 0 for i in class_items) if class_items else False},
            {'key': 'behavior_snapshots_ready', 'label': 'Có snapshot nhận định học online', 'passed': total_snapshots > 0},
            {'key': 'safe_policy', 'label': 'Chỉ dùng nhãn mềm, không kết luận vi phạm', 'passed': True},
        ]

        return {
            'version': getattr(settings, 'app_version', '25.9.16.7.2.64.12'),
            'pilot_status': pilot_status,
            'ready_for_pilot': pilot_status in {'PASS', 'PASS_WITH_WARNINGS'},
            'ready_for_broad_production': bool(production.get('ready_for_production')) and pilot_status == 'PASS',
            'blocker_count': len(blocker_codes),
            'warning_count': len(warning_codes),
            'blocker_codes': blocker_codes,
            'warning_codes': warning_codes,
            'filters': {'class_id': class_id, 'course_id': resolved_course_id, 'campus': campus, 'branch': branch, 'sample_limit': sample_limit},
            'checks': {
                'tracking_event_count': int(self.db.query(AnalyticsTrackingEvent.id).count() or 0),
                'behavior_snapshot_count': int(total_snapshots or 0),
                'session_progress_count': int(total_session_snapshots or 0),
                'video_progress_count': int(total_video_snapshots or 0),
                'pilot_class_count': len(class_items),
                'pilot_student_count': int(total_students or 0),
                'production_readiness': production.get('readiness'),
                'data_quality_readiness': data_quality.get('readiness'),
                'backfill_enqueueable_classes': (backfill.get('counters') or {}).get('enqueueable', 0),
            },
            'checklist': checklist,
            'classes': class_items,
            'sample_students': samples,
            'next_actions': [
                'Chạy ingest tracking log.' if not ingest.get('file_exists') or int(ingest.get('total_events_inserted') or 0) <= 0 else '',
                'Rebuild session structure nếu thiếu mapping Bài/Session.' if any((i.get('session_count') or 0) <= 0 for i in class_items) else '',
                'Chạy Backfill học online cho lớp pilot.' if total_snapshots <= 0 else '',
                'Đối chiếu thủ công 5 sinh viên mẫu với LMS/tracking log trước khi mở rộng.' if samples else '',
            ],
            'production_readiness': production,
            'data_quality': data_quality,
            'backfill_plan': backfill,
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.',
        }

    def analytics_uat_evidence_pack(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        sample_limit: int = 5,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Single read-only evidence bundle for UAT sign-off.

        Operators need one artifact that can be exported from a smoke test and
        attached to a UAT ticket. This method intentionally composes existing
        materialized reports only. It never scans raw tracking.log, never
        enqueues jobs, never recalculates, and never mutates data.
        """
        generated_at = datetime.utcnow()
        production = self.production_readiness_report(allowed_class_ids=allowed_class_ids)
        sla = self.analytics_sla_report(allowed_class_ids=allowed_class_ids, limit=20)
        pilot = self.pilot_acceptance_report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=sample_limit,
            allowed_class_ids=allowed_class_ids,
        )
        doctor = self.class_result_doctor(class_id=class_id, course_id=course_id) if class_id else None

        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for source_name, report in (
            ('production_readiness', production),
            ('sla', sla),
            ('pilot_acceptance', pilot),
        ):
            for issue in report.get('issues') or []:
                severity = str(issue.get('severity') or '').upper()
                item = dict(issue)
                item['source'] = source_name
                if severity in {'BLOCKER', 'ERROR'}:
                    blockers.append(item)
                elif severity == 'WARNING':
                    warnings.append(item)
        for code in pilot.get('blocker_codes') or []:
            if not any(str(item.get('code')) == str(code) and item.get('source') == 'pilot_acceptance' for item in blockers):
                blockers.append({'source': 'pilot_acceptance', 'severity': 'BLOCKER', 'code': code, 'message': code})
        for code in pilot.get('warning_codes') or []:
            if not any(str(item.get('code')) == str(code) and item.get('source') == 'pilot_acceptance' for item in warnings):
                warnings.append({'source': 'pilot_acceptance', 'severity': 'WARNING', 'code': code, 'message': code})
        if doctor and str(doctor.get('status') or '').lower() in {'blocked'}:
            blockers.append({
                'source': 'class_doctor',
                'severity': 'BLOCKER',
                'code': doctor.get('data_gap') or 'CLASS_DOCTOR_BLOCKED',
                'message': doctor.get('message') or 'Lớp chưa đủ điều kiện dữ liệu.',
                'action': doctor.get('recommended_action'),
            })

        evidence_status = 'PASS'
        if blockers:
            evidence_status = 'FAIL'
        elif warnings or not pilot.get('ready_for_pilot') or str(sla.get('sla_status') or '').upper() != 'OK':
            evidence_status = 'PASS_WITH_WARNINGS'

        next_actions: list[str] = []
        seen_actions: set[str] = set()
        for report in (production, sla, pilot, doctor or {}):
            for action in report.get('next_actions') or []:
                action_text = str(action or '').strip()
                if action_text and action_text not in seen_actions:
                    seen_actions.add(action_text)
                    next_actions.append(action_text)
            action_text = str(report.get('recommended_action') or '').strip()
            if action_text and action_text not in seen_actions:
                seen_actions.add(action_text)
                next_actions.append(action_text)

        return {
            'version': getattr(settings, 'app_version', '25.9.16.7.2.64.12'),
            'artifact_type': 'uat_evidence_pack',
            'evidence_status': evidence_status,
            'generated_at': generated_at.isoformat(),
            'filters': {
                'class_id': class_id,
                'course_id': course_id,
                'campus': campus,
                'branch': branch,
                'sample_limit': sample_limit,
            },
            'summary': {
                'ready_for_production': bool(production.get('ready_for_production')),
                'ready_for_pilot': bool(pilot.get('ready_for_pilot')),
                'ready_for_broad_production': bool(pilot.get('ready_for_broad_production')),
                'sla_status': sla.get('sla_status'),
                'pilot_status': pilot.get('pilot_status'),
                'blocker_count': len(blockers),
                'warning_count': len(warnings),
                'pilot_class_count': len(pilot.get('classes') or []),
                'sample_student_count': len(pilot.get('sample_students') or []),
            },
            'blockers': blockers[:20],
            'warnings': warnings[:20],
            'next_actions': next_actions[:20],
            'reports': {
                'production_readiness': production,
                'sla': sla,
                'pilot_acceptance': pilot,
                'class_doctor': doctor,
            },
            'safe_policy': 'signals_only_not_violation',
            'read_only_guarantees': [
                'Không đọc raw tracking.log trong request.',
                'Không enqueue job trong request.',
                'Không recalculate trong request.',
                'Không mutate dữ liệu.',
                'Không kết luận vi phạm cá nhân.',
            ],
            'disclaimer': 'Evidence pack dùng cho nghiệm thu UAT/pilot vận hành analytics; mọi nhận định cá nhân vẫn là tín hiệu mềm cần giáo viên/quản lý xác minh.',
        }
