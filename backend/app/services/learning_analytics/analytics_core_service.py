from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob, AcademicCourseMapping, AcademicQuizDeadlineOverride, AcademicStudent, AcademicStudentLearningSnapshot, AcademicSubject, AcademicTerm
from app.models.learning_analytics import (
    AnalyticsCourseSession,
    AnalyticsIngestCheckpoint,
    AnalyticsLearningBehaviorSnapshot,
    AnalyticsQuizAttempt,
    AnalyticsStudentSessionProgress,
    AnalyticsStudentVideoProgress,
    AnalyticsTrackingEvent,
)
from app.services.learning_analytics.learning_behavior_classifier import BehaviorInput, classify_learning_behavior
from app.services.learning_analytics.session_deadline_mapper import build_session_mappings_from_blocks, week_for_session
from app.services.academic_service import AcademicService
from app.services.learning_analytics.tracking_event_parser import TrackingParseError, parse_tracking_log_line
from app.services.learning_analytics.quiz_attempt_analyzer import EventLike, build_quiz_attempt_features
from app.services.learning_analytics.tracking_log_reader import TrackingLogReader
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress

VIDEO_EVENT_TYPES = {'play_video', 'pause_video', 'stop_video', 'seek_video', 'edx.video.played', 'edx.video.paused', 'edx.video.stopped', 'edx.video.position.changed'}
PROBLEM_EVENT_TYPES = {'problem_check', 'problem_graded', 'problem_save', 'edx.grades.problem.submitted', 'edx.completion.block_completion.changed'}
QUIZ_SESSION_EVENT_TYPES = {'/api/unit-reset/v1/quiz-session/start', '/api/unit-reset/v1/quiz-session/status', '/api/unit-reset/v1/quiz-session/reset'}
ITEMBANK_EVENT_TYPES = {'edx.itembankblock.content.assigned'}
ANSWER_REVEAL_EVENT_TYPES = {'problem_show', 'showanswer'}
QUIZ_ANALYTICS_EVENT_TYPES = PROBLEM_EVENT_TYPES | QUIZ_SESSION_EVENT_TYPES | ITEMBANK_EVENT_TYPES | ANSWER_REVEAL_EVENT_TYPES
ANALYTICS_INGEST_LOCK_ID = 2591672601


class LearningAnalyticsCoreService:
    def __init__(self, db: Session):
        self.db = db

    def schema_inspect(self) -> dict[str, Any]:
        """Phase 0 report: what is reused and what the analytics core adds."""
        return {
            'version': '25.9.16.7.2.7',
            'principle': 'Tái sử dụng schema hiện có, chỉ bổ sung bảng thiếu cho raw normalized events và analytics snapshot.',
            'reused_models': [
                'AcademicTerm / AcademicBlock: nguồn học kỳ, block, deadline 6 tuần nếu đã cấu hình ở /semesters',
                'AcademicClass / AcademicClassStudent / AcademicStudent: mapping lớp -> sinh viên',
                'AcademicTeacherAssignment: mapping giáo viên -> lớp',
                'AcademicClassCourseMapping / AcademicCourseMapping: mapping lớp/môn -> Open edX course_id',
                'AcademicStudentLearningSnapshot: progress/grade Course CMS hiện có',
                'AcademicQuizDeadlineOverride: manual deadline/quiz override nếu đã cấu hình',
                'AcademicClassSyncJob / AcademicSyncRun: job/sync/audit pattern hiện có',
                'AuditLog + log_audit: ghi audit cho ingest/recalculate/export sau các phase UI',
                'BusinessRBACService: SYSTEM_ADMIN/CAMPUS_MANAGER/teacher scope',
            ],
            'new_models': [
                'AnalyticsIngestCheckpoint: offset/checkpoint để không đọc full tracking.log mỗi request',
                'AnalyticsTrackingEvent: normalized tracking events, chống trùng raw_line_hash',
                'AnalyticsCourseSession: course -> Bài/Session -> video/quiz/deadline snapshot',
                'AnalyticsStudentVideoProgress: video progress snapshot',
                'AnalyticsStudentSessionProgress: tiến độ theo Bài/Session',
                'AnalyticsLearningBehaviorSnapshot: nhận định mềm theo sinh viên/lớp/course',
            ],
            'why_new_schema_is_needed': [
                'Project chưa có bảng normalized tracking.log events.',
                'Project chưa có checkpoint ingest offset/log rotate.',
                'Project chưa có snapshot theo video/session/deadline để dashboard không query raw log trực tiếp.',
            ],
            'no_duplicate_tables_created_for': [
                'job status chung', 'audit log', 'RBAC', 'class/student/course mapping', 'CMS progress/grade snapshot', 'semester/deadline config'
            ],
            'deadline_source_order': ['academic_quiz_deadline_overrides / deadline đã cấu hình cho Quiz', '/semesters learning_weeks', 'AcademicTerm/Block dates', 'infer 6 tuần theo thứ tự session nếu thật sự thiếu'],
            'safety_policy': 'Frontend/API chỉ trả nhãn mềm: dấu hiệu nghi vấn, không kết luận vi phạm.',
        }

    def _is_postgres(self) -> bool:
        bind = self.db.get_bind()
        return bool(bind is not None and getattr(bind.dialect, 'name', '') == 'postgresql')

    def _try_acquire_ingest_lock(self) -> bool:
        # PostgreSQL session-level advisory lock prevents beat/manual ingest overlap.
        # Non-PostgreSQL test databases do not support advisory locks, so they run
        # single-process without the lock.
        if not self._is_postgres():
            return True
        return bool(
            self.db.execute(
                text('SELECT pg_try_advisory_lock(:lock_id)'),
                {'lock_id': ANALYTICS_INGEST_LOCK_ID},
            ).scalar()
        )

    def _release_ingest_lock(self) -> None:
        if not self._is_postgres():
            return
        self.db.execute(
            text('SELECT pg_advisory_unlock(:lock_id)'),
            {'lock_id': ANALYTICS_INGEST_LOCK_ID},
        )

    def _get_checkpoint(self, key: str, file_path: str) -> AnalyticsIngestCheckpoint:
        cp = (
            self.db.query(AnalyticsIngestCheckpoint)
            .filter(AnalyticsIngestCheckpoint.checkpoint_key == key)
            .with_for_update()
            .first()
        )
        if cp:
            if file_path and cp.file_path != file_path:
                cp.file_path = file_path
            return cp
        cp = AnalyticsIngestCheckpoint(checkpoint_key=key, file_path=file_path, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        self.db.add(cp)
        self.db.flush()
        return cp

    def ingest_status(self) -> dict[str, Any]:
        file_path = getattr(settings, 'openedx_tracking_log_path', '/openedx-data/lms/logs/tracking.log')
        cp = self.db.query(AnalyticsIngestCheckpoint).filter(AnalyticsIngestCheckpoint.checkpoint_key == 'openedx_tracking_log').first()
        exists = Path(file_path).exists()
        return {
            'enabled': bool(getattr(settings, 'analytics_ingest_enabled', True)),
            'file_path': file_path,
            'file_exists': exists,
            'last_offset': int(cp.last_offset or 0) if cp else 0,
            'last_run_at': cp.last_run_at.isoformat() if cp and cp.last_run_at else None,
            'last_status': cp.last_status if cp else 'never_run',
            'last_error': cp.last_error if cp else None,
            'total_lines_read': int(cp.total_lines_read or 0) if cp else 0,
            'total_events_inserted': int(cp.total_events_inserted or 0) if cp else 0,
            'total_duplicate_events': int(cp.total_duplicate_events or 0) if cp else 0,
            'total_parse_errors': int(cp.total_parse_errors or 0) if cp else 0,
            'stats': cp.stats_json if cp else {},
        }

    def _class_scope_filter(self, q: Any, column: Any, value: Any) -> Any:
        """Apply AcademicCourseMapping scope fields to AcademicClass safely.

        AP/CMS data can store campus/branch/block as NULL or empty strings for
        broad mappings. Keep this helper conservative: a scoped mapping must
        match exactly, while a blank mapping only matches blank class scope.
        """
        if value is None or str(value).strip() == '':
            return q.filter(or_(column.is_(None), column == ''))
        return q.filter(column == value)

    def _resolve_recalculate_class_ids_for_courses(self, *, course_ids: set[str]) -> dict[str, set[str]]:
        """Resolve Open edX course IDs to AP class IDs using existing mappings.

        Direct class mappings win. Subject/term course mappings are used as a
        fallback so post-ingest orchestration can still enqueue class jobs even
        when the course is mapped at the subject scope rather than the class
        override scope.
        """
        clean_course_ids = {str(course_id or '').strip() for course_id in course_ids if str(course_id or '').strip()}
        if not clean_course_ids:
            return {}
        resolved: dict[str, set[str]] = defaultdict(set)
        direct_rows = (
            self.db.query(AcademicClassCourseMapping.openedx_course_id, AcademicClassCourseMapping.class_id)
            .join(AcademicClass, AcademicClass.id == AcademicClassCourseMapping.class_id)
            .filter(
                AcademicClassCourseMapping.active.is_(True),
                AcademicClass.active.is_(True),
                AcademicClassCourseMapping.openedx_course_id.in_(list(clean_course_ids)),
            )
            .all()
        )
        for course_id, class_id in direct_rows:
            if course_id and class_id:
                resolved[str(course_id)].add(str(class_id))

        subject_mappings = (
            self.db.query(AcademicCourseMapping)
            .filter(
                AcademicCourseMapping.active.is_(True),
                AcademicCourseMapping.openedx_course_id.in_(list(clean_course_ids)),
            )
            .all()
        )
        for mapping in subject_mappings:
            q = self.db.query(AcademicClass.id).filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id == mapping.term_id,
                AcademicClass.subject_id == mapping.subject_id,
            )
            q = self._class_scope_filter(q, AcademicClass.block_id, mapping.block_id)
            q = self._class_scope_filter(q, AcademicClass.campus, mapping.campus)
            q = self._class_scope_filter(q, AcademicClass.branch, mapping.branch)
            for (class_id,) in q.all():
                if class_id:
                    resolved[str(mapping.openedx_course_id)].add(str(class_id))
        return resolved

    def enqueue_post_ingest_recalculate_jobs(
        self,
        *,
        course_usernames: dict[str, set[str]],
        source: str = 'analytics_ingest_task',
    ) -> dict[str, Any]:
        """Queue production-safe recalculation after ingest.

        This deliberately does not recalculate every student or every course on
        every scheduler tick. It only considers courses that received newly
        inserted tracking events, resolves them to AP classes, then enqueues at
        most a bounded number of class-level jobs. Existing queued/running jobs
        and recent completed jobs debounce noisy tracking.log bursts.
        """
        if not bool(getattr(settings, 'analytics_post_ingest_recalculate_enabled', True)):
            return {'enabled': False, 'status': 'disabled', 'message': 'ANALYTICS_POST_INGEST_RECALCULATE_ENABLED=false'}
        course_ids = {str(course_id or '').strip() for course_id in (course_usernames or {}).keys() if str(course_id or '').strip()}
        if not course_ids:
            return {'enabled': True, 'status': 'no_impacted_courses', 'courses': 0, 'queued_jobs': 0}

        class_ids_by_course = self._resolve_recalculate_class_ids_for_courses(course_ids=course_ids)
        cooldown_seconds = int(getattr(settings, 'analytics_post_ingest_recalculate_cooldown_seconds', 900) or 900)
        max_jobs_per_run = max(1, int(getattr(settings, 'analytics_post_ingest_recalculate_max_jobs_per_run', 10) or 10))
        max_active = max(1, int(getattr(settings, 'analytics_backfill_max_active_jobs', 20) or 20))
        safe_limit = max(1, min(int(getattr(settings, 'analytics_recalculate_max_students_per_job', 500) or 500), 5000))
        now = datetime.utcnow()
        queued: list[dict[str, Any]] = []
        skipped: Counter[str] = Counter()
        considered = 0

        # Highest-impact courses first. The event count is not used as a score
        # for students; it only prioritizes which class jobs enter the queue
        # when the run cap is reached.
        sorted_courses = sorted(course_ids, key=lambda cid: len(course_usernames.get(cid) or set()), reverse=True)
        from app.worker import analytics_class_recalculate_task

        for course_id in sorted_courses:
            class_ids = sorted(class_ids_by_course.get(course_id) or set())
            if not class_ids:
                skipped['NO_CLASS_MAPPING'] += 1
                continue
            impacted_users = sorted(str(u) for u in (course_usernames.get(course_id) or set()) if str(u or '').strip())
            for class_id in class_ids:
                considered += 1
                if len(queued) >= max_jobs_per_run:
                    skipped['RUN_JOB_CAP_REACHED'] += 1
                    break
                active_global = self.db.query(AcademicClassSyncJob).filter(
                    AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
                    AcademicClassSyncJob.status.in_(['queued', 'running']),
                ).count()
                if active_global >= max_active:
                    skipped['TOO_MANY_ACTIVE_ANALYTICS_JOBS'] += 1
                    break
                active_for_class = self.db.query(AcademicClassSyncJob).filter(
                    AcademicClassSyncJob.class_id == class_id,
                    AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
                    AcademicClassSyncJob.status.in_(['queued', 'running']),
                ).order_by(AcademicClassSyncJob.created_at.desc()).first()
                if active_for_class:
                    skipped['CLASS_JOB_ALREADY_ACTIVE'] += 1
                    continue
                recent_for_class = self.db.query(AcademicClassSyncJob).filter(
                    AcademicClassSyncJob.class_id == class_id,
                    AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
                    AcademicClassSyncJob.created_at >= now - timedelta(seconds=cooldown_seconds),
                ).order_by(AcademicClassSyncJob.created_at.desc()).first()
                if recent_for_class:
                    skipped['CLASS_COOLDOWN_ACTIVE'] += 1
                    continue
                job = AcademicClassSyncJob(
                    job_type='learning_analytics_recalculate',
                    status='queued',
                    class_id=class_id,
                    requested_by='system:analytics-ingest',
                    force=False,
                    limit=safe_limit,
                    progress_current=0,
                    progress_total=100,
                    progress_label='Đang chờ tính lại sau ingest tracking.log',
                    request_json=json_safe_value({
                        'course_id': course_id,
                        'username': None,
                        'force': False,
                        'limit': safe_limit,
                        'source': source,
                        'cooldown_seconds': cooldown_seconds,
                        'impacted_user_count': len(impacted_users),
                        'impacted_usernames_sample': impacted_users[:20],
                        'signals_only_not_violation': True,
                    }),
                    result_json={},
                )
                self.db.add(job)
                self.db.commit()
                async_result = analytics_class_recalculate_task.delay(job.id)
                data = job.request_json if isinstance(job.request_json, dict) else {}
                data['enqueue'] = {'task_name': 'analytics_class_recalculate_task', 'celery_task_id': getattr(async_result, 'id', None)}
                job.request_json = json_safe_value(data)
                self.db.add(job)
                self.db.commit()
                queued.append({'job_id': job.id, 'class_id': class_id, 'course_id': course_id, 'impacted_user_count': len(impacted_users)})
            if len(queued) >= max_jobs_per_run:
                break

        return {
            'enabled': True,
            'status': 'completed',
            'courses': len(course_ids),
            'mapped_courses': len([cid for cid in course_ids if class_ids_by_course.get(cid)]),
            'considered_class_jobs': considered,
            'queued_jobs': len(queued),
            'queued': queued,
            'skipped': dict(skipped),
            'cooldown_seconds': cooldown_seconds,
            'max_jobs_per_run': max_jobs_per_run,
            'max_active_jobs': max_active,
            'safe_policy': 'signals_only_not_violation',
        }

    def run_ingest(self, *, file_path: str | None = None, max_lines: int | None = None) -> dict[str, Any]:
        if not bool(getattr(settings, 'analytics_ingest_enabled', True)):
            return {'enabled': False, 'status': 'disabled', 'message': 'ANALYTICS_INGEST_ENABLED=false'}
        if not self._try_acquire_ingest_lock():
            return {
                'enabled': True,
                'status': 'skipped_locked',
                'message': 'Một lượt ingest tracking log khác đang chạy.',
                'safe_policy': 'signals_only_not_violation',
            }
        try:
            path = file_path or getattr(settings, 'openedx_tracking_log_path', '/openedx-data/lms/logs/tracking.log')
            cp = self._get_checkpoint('openedx_tracking_log', path)
            reader = TrackingLogReader(path, max_lines=max_lines or getattr(settings, 'analytics_max_lines_per_run', 50000))
            result = reader.read_from(last_offset=cp.last_offset, last_inode=cp.file_inode)
            stats = Counter()
            stats['lines_read'] = len(result.lines)
            if not result.file_exists:
                cp.last_status = 'missing_file'
                cp.last_error = 'tracking_log_not_found'
                cp.last_run_at = datetime.utcnow()
                cp.stats_json = dict(stats)
                self.db.commit()
                return {'status': 'missing_file', 'file_path': path, 'file_exists': False, **dict(stats)}
            event_type_counts: Counter[str] = Counter()
            impacted_course_usernames: dict[str, set[str]] = defaultdict(set)
            for line in result.lines:
                try:
                    parsed = parse_tracking_log_line(line)
                except TrackingParseError:
                    stats['parse_errors'] += 1
                    continue
                if parsed is None:
                    stats['ignored_events'] += 1
                    continue
                event_type_counts[parsed.event_type] += 1
                existing = self.db.query(AnalyticsTrackingEvent.id).filter(AnalyticsTrackingEvent.raw_line_hash == parsed.raw_line_hash).first()
                if existing:
                    stats['duplicate_events'] += 1
                    continue
                self.db.add(AnalyticsTrackingEvent(**parsed.as_model_kwargs()))
                stats['events_inserted'] += 1
                if parsed.course_id:
                    impacted_course_usernames[str(parsed.course_id or '').strip()].add(str(parsed.username or '').strip())
                if parsed.event_type in VIDEO_EVENT_TYPES:
                    stats['video_events'] += 1
                if parsed.event_type in PROBLEM_EVENT_TYPES:
                    stats['problem_events'] += 1
                if (stats['events_inserted'] % 500) == 0:
                    try:
                        self.db.flush()
                    except IntegrityError:
                        # Race safety: the advisory lock should prevent this in
                        # normal flow, but keep ingest resilient if a duplicate
                        # row was inserted by an older worker or manual process.
                        self.db.rollback()
                        cp = self._get_checkpoint('openedx_tracking_log', path)
                        stats['duplicate_events'] += 1
            cp.file_inode = result.file_inode
            cp.file_size = result.file_size
            cp.last_offset = result.end_offset
            cp.last_run_at = datetime.utcnow()
            cp.last_status = 'completed'
            cp.last_error = None
            cp.total_lines_read = int(cp.total_lines_read or 0) + int(stats['lines_read'])
            cp.total_events_inserted = int(cp.total_events_inserted or 0) + int(stats['events_inserted'])
            cp.total_duplicate_events = int(cp.total_duplicate_events or 0) + int(stats['duplicate_events'])
            cp.total_parse_errors = int(cp.total_parse_errors or 0) + int(stats['parse_errors'])
            impacted_course_usernames = {
                course_id: {username for username in usernames if username}
                for course_id, usernames in impacted_course_usernames.items()
                if course_id
            }
            cp.stats_json = {
                **dict(stats),
                'event_type_counts': dict(event_type_counts),
                'start_offset': result.start_offset,
                'end_offset': result.end_offset,
                'rotated': result.rotated,
                'impacted_course_count': len(impacted_course_usernames),
                'impacted_user_count': sum(len(users) for users in impacted_course_usernames.values()),
            }
            self.db.commit()
            post_ingest_recalculate = {'enabled': bool(getattr(settings, 'analytics_post_ingest_recalculate_enabled', True)), 'status': 'not_run'}
            if int(stats['events_inserted'] or 0) > 0:
                try:
                    post_ingest_recalculate = self.enqueue_post_ingest_recalculate_jobs(
                        course_usernames=impacted_course_usernames,
                        source='analytics_ingest_task',
                    )
                except Exception as exc:
                    post_ingest_recalculate = {'enabled': True, 'status': 'failed', 'message': str(exc)[:1000]}
            cp.stats_json = {**(cp.stats_json or {}), 'post_ingest_recalculate': post_ingest_recalculate}
            self.db.add(cp)
            self.db.commit()
            return {'enabled': True, 'status': 'completed', 'file_path': path, 'file_exists': True, 'last_offset': result.end_offset, **cp.stats_json}
        finally:
            self._release_ingest_lock()

    def rebuild_session_structure_from_blocks(
        self,
        *,
        course_id: str,
        blocks: list[dict[str, Any]],
        course_start_at: datetime | None = None,
    ) -> dict[str, Any]:
        mappings = build_session_mappings_from_blocks(course_id, blocks, course_start_at=course_start_at)
        now = datetime.utcnow()
        saved = 0
        for mapping in mappings:
            row = self.db.query(AnalyticsCourseSession).filter(
                AnalyticsCourseSession.course_id == course_id,
                AnalyticsCourseSession.session_index == mapping.session_index,
            ).first()
            if not row:
                row = AnalyticsCourseSession(course_id=course_id, session_index=mapping.session_index, session_key=mapping.session_key, created_at=now, updated_at=now)
                self.db.add(row)
            row.session_key = mapping.session_key
            row.session_title = mapping.session_title
            row.week_index = mapping.week_index
            row.deadline_at = mapping.deadline_at
            row.deadline_source = mapping.deadline_source
            row.deadline_mapping_quality = mapping.deadline_mapping_quality
            row.total_parts = len([c for c in mapping.components if c.block_type == 'video'])
            row.total_videos = len([c for c in mapping.components if c.block_type == 'video'])
            row.quiz_usage_key = mapping.quiz.usage_key if mapping.quiz else None
            row.components_json = {'components': [asdict(c) for c in mapping.components]}
            row.session_type = mapping.session_type
            row.source = 'blocks_adapter'
            row.active = True
            row.rebuilt_at = now
            row.updated_at = now
            saved += 1
        self.db.commit()
        return {'course_id': course_id, 'session_count': len(mappings), 'saved': saved, 'deadline_pattern': [week_for_session(i, len(mappings) or 1) for i in range(1, len(mappings) + 1)]}

    def _quiz_deadline_overrides_by_session(self, *, class_id: str | None, course_id: str | None) -> dict[int, AcademicQuizDeadlineOverride]:
        if not class_id:
            return {}
        query = self.db.query(AcademicQuizDeadlineOverride).filter(AcademicQuizDeadlineOverride.class_id == class_id)
        if course_id:
            query = query.filter((AcademicQuizDeadlineOverride.course_id == course_id) | (AcademicQuizDeadlineOverride.course_id.is_(None)))
        result: dict[int, AcademicQuizDeadlineOverride] = {}
        for row in query.order_by(AcademicQuizDeadlineOverride.updated_at.desc().nullslast()).all():
            if row.quiz_number and int(row.quiz_number) not in result:
                result[int(row.quiz_number)] = row
        return result

    def get_session_structure(self, *, course_id: str, class_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.db.query(AnalyticsCourseSession).filter(AnalyticsCourseSession.course_id == course_id, AnalyticsCourseSession.active == True).order_by(AnalyticsCourseSession.session_index.asc()).all()
        overrides = self._quiz_deadline_overrides_by_session(class_id=class_id, course_id=course_id)
        result: list[dict[str, Any]] = []
        for r in rows:
            override = overrides.get(int(r.session_index or 0))
            deadline_at = override.deadline_date if override and override.deadline_date else r.deadline_at
            source = 'QUIZ_DEADLINE' if override and override.deadline_date else r.deadline_source
            quality = 'GOOD' if override and override.deadline_date else r.deadline_mapping_quality
            components = (r.components_json or {}).get('components', [])
            if override:
                components = [dict(item) for item in components]
                for item in components:
                    if str(item.get('block_type') or '').lower() in {'problem', 'quiz', 'sequential_quiz'}:
                        item['deadline_at'] = deadline_at.isoformat() if deadline_at else None
                        item['deadline_source'] = source
                        item['component_label'] = override.component_label or item.get('title') or item.get('usage_key')
            result.append({
                'session_index': r.session_index,
                'session_key': r.session_key,
                'session_title': r.session_title,
                'session_type': getattr(r, 'session_type', 'LEARNING_SESSION') or 'LEARNING_SESSION',
                'week_index': r.week_index,
                'deadline_at': deadline_at.isoformat() if deadline_at else None,
                'deadline_source': source,
                'deadline_mapping_quality': quality,
                'total_parts': r.total_parts,
                'total_videos': r.total_videos,
                'quiz_usage_key': r.quiz_usage_key,
                'quiz_deadline_configured': bool(override and override.deadline_date),
                'quiz_deadline_label': override.component_label if override else None,
                'components': components,
            })
        return result

    @staticmethod
    def _string_match_score(needle: str | None, haystack: str | None) -> int:
        left = str(needle or '').strip().lower()
        right = str(haystack or '').strip().lower()
        if not left or not right:
            return 0
        if left == right:
            return 4
        if left in right or right in left:
            return 2
        left_tail = left.split('@')[-1].split('/')[-1]
        right_tail = right.split('@')[-1].split('/')[-1]
        if left_tail and right_tail and (left_tail == right_tail or left_tail in right_tail or right_tail in left_tail):
            return 1
        return 0

    def _video_session_lookup(self, *, course_id: str) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for session in self.get_session_structure(course_id=course_id):
            for component in session.get('components') or []:
                if str(component.get('block_type') or '').lower() != 'video':
                    continue
                keys = {component.get('usage_key'), component.get('id'), component.get('code'), component.get('video_id')}
                for key in keys:
                    if key:
                        lookup[str(key)] = {'session': session, 'component': component}
        return lookup

    def _match_video_session(self, *, video_id: str | None, video_code: str | None, lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        candidates = [video_id, video_code]
        for candidate in candidates:
            if candidate and str(candidate) in lookup:
                return lookup[str(candidate)]
        best: tuple[int, dict[str, Any] | None] = (0, None)
        for key, value in lookup.items():
            score = max(self._string_match_score(video_id, key), self._string_match_score(video_code, key))
            if score > best[0]:
                best = (score, value)
        return best[1] if best[0] > 0 else None

    def recalculate_course_video_progress(self, *, course_id: str, username: str | None = None) -> dict[str, Any]:
        video_session_lookup = self._video_session_lookup(course_id=course_id)
        query = self.db.query(AnalyticsTrackingEvent).filter(AnalyticsTrackingEvent.course_id == course_id, AnalyticsTrackingEvent.event_type.in_(list(VIDEO_EVENT_TYPES)))
        if username:
            query = query.filter(AnalyticsTrackingEvent.username == username)
        events = query.order_by(AnalyticsTrackingEvent.username.asc(), AnalyticsTrackingEvent.video_id.asc(), AnalyticsTrackingEvent.event_time.asc()).all()
        grouped: dict[tuple[str, str], list[AnalyticsTrackingEvent]] = defaultdict(list)
        for ev in events:
            if not ev.username or not ev.video_id:
                continue
            grouped[(ev.username, ev.video_id)].append(ev)
        now = datetime.utcnow()
        saved = 0
        for (user, video_id), group in grouped.items():
            result = calculate_video_progress([
                VideoEventInput(e.event_type, e.event_time, e.current_time_seconds, e.video_duration_seconds, e.raw_event or {}) for e in group
            ], complete_threshold=getattr(settings, 'analytics_video_complete_threshold', 0.9), suspicious_watch_ratio=getattr(settings, 'analytics_suspicious_watch_ratio', 0.25), max_passive_segment_seconds=getattr(settings, 'analytics_max_passive_segment_seconds', 600))
            row = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.course_id == course_id, AnalyticsStudentVideoProgress.username == user, AnalyticsStudentVideoProgress.video_id == video_id).first()
            if not row:
                row = AnalyticsStudentVideoProgress(course_id=course_id, username=user, video_id=video_id)
                self.db.add(row)
            matched_session = self._match_video_session(video_id=video_id, video_code=group[-1].video_code, lookup=video_session_lookup)
            row.user_id = group[-1].user_id
            row.video_code = group[-1].video_code
            if matched_session:
                session = matched_session.get('session') or {}
                component = matched_session.get('component') or {}
                row.session_key = session.get('session_key')
                row.session_index = session.get('session_index')
                row.component_title = component.get('title') or component.get('display_name') or row.component_title or ''
            row.duration_seconds = result.duration_seconds
            row.max_position_seconds = result.max_position_seconds
            row.completion_percent = result.completion_percent
            row.estimated_watch_seconds = result.estimated_watch_seconds
            row.estimated_watch_percent = result.estimated_watch_percent
            row.consistency_percent = result.consistency_percent
            row.video_quality_percent = result.video_quality_percent
            row.long_passive_segment_count = result.long_passive_segment_count
            row.long_passive_seconds = result.long_passive_seconds
            row.passive_watch_seconds = result.passive_watch_seconds
            row.play_count = result.play_count
            row.pause_count = result.pause_count
            row.stop_count = result.stop_count
            row.seek_count = result.seek_count
            row.is_completed = result.is_completed
            row.is_suspicious = result.is_suspicious
            row.suspicious_reason = ','.join(result.reason_codes)
            row.evidence_json = result.evidence
            row.first_played_at = min([e.event_time for e in group if e.event_time] or [None])
            row.last_event_at = max([e.event_time for e in group if e.event_time] or [None])
            row.calculated_at = now
            saved += 1
        self.db.commit()
        return {'course_id': course_id, 'username': username, 'video_progress_rows': saved}

    def recalculate_course_quiz_attempts(self, *, course_id: str, username: str | None = None) -> dict[str, Any]:
        query = self.db.query(AnalyticsTrackingEvent).filter(
            AnalyticsTrackingEvent.course_id == course_id,
            AnalyticsTrackingEvent.event_type.in_(list(QUIZ_ANALYTICS_EVENT_TYPES)),
        )
        if username:
            query = query.filter(AnalyticsTrackingEvent.username == username)
        rows = query.order_by(AnalyticsTrackingEvent.username.asc(), AnalyticsTrackingEvent.event_time.asc()).all()
        features = build_quiz_attempt_features([
            EventLike(
                event_type=r.event_type,
                event_source=r.event_source,
                event_time=r.event_time,
                user_id=r.user_id,
                username=r.username,
                course_id=r.course_id,
                page_url=r.page_url,
                raw_event=r.raw_event or {},
                raw_context=r.raw_context or {},
                raw_json=r.raw_json or {},
            )
            for r in rows
        ])
        now = datetime.utcnow()
        saved = 0
        for feat in features:
            row = self.db.query(AnalyticsQuizAttempt).filter(
                AnalyticsQuizAttempt.course_id == feat.course_id,
                AnalyticsQuizAttempt.username == feat.username,
                AnalyticsQuizAttempt.unit_usage_key == feat.unit_usage_key,
                AnalyticsQuizAttempt.attempt_no == feat.attempt_no,
            ).first()
            if not row:
                row = AnalyticsQuizAttempt(course_id=feat.course_id, username=feat.username, unit_usage_key=feat.unit_usage_key, attempt_no=feat.attempt_no)
                self.db.add(row)
            row.user_id = feat.user_id
            row.sequence_usage_key = feat.sequence_usage_key
            row.unit_reset_nonce = feat.unit_reset_nonce
            row.started_at = feat.started_at
            row.ended_at = feat.ended_at
            row.reset_count = int(feat.reset_count or 0)
            row.submission_count = len(feat.submissions)
            row.assigned_problem_usage_keys_json = feat.assigned_problem_usage_keys
            row.itembank_locations_json = feat.itembank_locations
            row.score_earned = feat.score_earned
            row.score_possible = feat.score_possible
            row.median_time_per_question_seconds = feat.median_time_per_question_seconds
            row.repeat_rate = feat.repeat_rate
            row.suspicious_quiz_speed = bool(feat.suspicious_quiz_speed)
            row.fishing_pattern = bool(feat.fishing_pattern)
            row.showanswer_count = int(feat.showanswer_count or 0)
            row.first_submission_at = feat.first_submission_at
            row.last_submission_at = feat.last_submission_at
            row.low_confidence_reason = feat.low_confidence_reason
            row.evidence_json = feat.evidence
            row.calculated_at = now
            saved += 1
        self.db.commit()
        return {'course_id': course_id, 'username': username, 'quiz_attempt_rows': saved}

    @staticmethod
    def _key_match(left: str | None, right: str | None) -> bool:
        a = str(left or '').strip()
        b = str(right or '').strip()
        if not a or not b:
            return False
        return a == b or a in b or b in a

    def _quiz_attempts_for_user(self, *, course_id: str, username: str) -> list[AnalyticsQuizAttempt]:
        return self.db.query(AnalyticsQuizAttempt).filter(
            AnalyticsQuizAttempt.course_id == course_id,
            AnalyticsQuizAttempt.username == username,
        ).order_by(AnalyticsQuizAttempt.started_at.asc().nullslast(), AnalyticsQuizAttempt.attempt_no.asc()).all()

    def _quiz_attempt_for_session(self, *, attempts: list[AnalyticsQuizAttempt], session: dict[str, Any]) -> AnalyticsQuizAttempt | None:
        quiz_key = session.get('quiz_usage_key')
        session_key = session.get('session_key')
        components = session.get('components') if isinstance(session.get('components'), list) else []
        candidate_keys = [str(quiz_key or ''), str(session_key or '')]
        candidate_keys.extend(str(item.get('usage_key') or item.get('id') or '') for item in components if isinstance(item, dict))
        for attempt in reversed(attempts):
            if any(self._key_match(attempt.unit_usage_key, key) or self._key_match(attempt.sequence_usage_key, key) for key in candidate_keys if key):
                return attempt
            assigned = attempt.assigned_problem_usage_keys_json or []
            if any(any(self._key_match(value, key) for key in candidate_keys if key) for value in assigned):
                return attempt
        return None

    def _student_usernames_for_class(self, *, class_id: str | None, course_id: str, username: str | None = None) -> list[str]:
        if username:
            return [username]
        users: set[str] = set()
        if class_id:
            rows = (
                self.db.query(AcademicStudent.username)
                .join(AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id)
                .filter(AcademicClassStudent.class_id == class_id)
                .all()
            )
            return sorted({str(row[0]) for row in rows if row and row[0]})
        video_users = self.db.query(AnalyticsStudentVideoProgress.username).filter(AnalyticsStudentVideoProgress.course_id == course_id).distinct().all()
        users.update(str(item[0]) for item in video_users if item and item[0])
        event_users = self.db.query(AnalyticsTrackingEvent.username).filter(AnalyticsTrackingEvent.course_id == course_id).distinct().all()
        users.update(str(item[0]) for item in event_users if item and item[0])
        return sorted(users)

    def _learning_snapshots_by_username(self, *, class_id: str | None, course_id: str) -> dict[str, AcademicStudentLearningSnapshot]:
        if not class_id:
            return {}
        rows = self.db.query(AcademicStudent.username, AcademicStudentLearningSnapshot).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(
            AcademicStudentLearningSnapshot,
            (AcademicStudentLearningSnapshot.student_id == AcademicStudent.id)
            & (AcademicStudentLearningSnapshot.class_id == class_id)
            & (AcademicStudentLearningSnapshot.openedx_course_id == course_id),
        ).filter(AcademicClassStudent.class_id == class_id).all()
        return {str(username): snapshot for username, snapshot in rows if username and snapshot}


    def _events_count_by_username(self, *, course_id: str, usernames: list[str]) -> dict[str, int]:
        if not usernames:
            return {}
        rows = (
            self.db.query(AnalyticsTrackingEvent.username, func.count(AnalyticsTrackingEvent.id))
            .filter(
                AnalyticsTrackingEvent.course_id == course_id,
                AnalyticsTrackingEvent.username.in_(usernames),
            )
            .group_by(AnalyticsTrackingEvent.username)
            .all()
        )
        return {str(user): int(count or 0) for user, count in rows if user}

    def _video_progress_by_username(self, *, course_id: str, usernames: list[str]) -> dict[str, list[AnalyticsStudentVideoProgress]]:
        if not usernames:
            return {}
        rows = (
            self.db.query(AnalyticsStudentVideoProgress)
            .filter(
                AnalyticsStudentVideoProgress.course_id == course_id,
                AnalyticsStudentVideoProgress.username.in_(usernames),
            )
            .all()
        )
        grouped: dict[str, list[AnalyticsStudentVideoProgress]] = defaultdict(list)
        for row in rows:
            grouped[str(row.username)].append(row)
        return grouped

    def _session_progress_by_username(self, *, course_id: str, usernames: list[str]) -> dict[str, list[AnalyticsStudentSessionProgress]]:
        if not usernames:
            return {}
        rows = (
            self.db.query(AnalyticsStudentSessionProgress)
            .filter(
                AnalyticsStudentSessionProgress.course_id == course_id,
                AnalyticsStudentSessionProgress.username.in_(usernames),
            )
            .all()
        )
        grouped: dict[str, list[AnalyticsStudentSessionProgress]] = defaultdict(list)
        for row in rows:
            grouped[str(row.username)].append(row)
        return grouped

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                return None
        return None

    def _quiz_item_for_session(self, *, components: list[dict[str, Any]], session_index: int, academic_service: AcademicService) -> dict[str, Any] | None:
        for item in components:
            try:
                numbers = academic_service._quiz_numbers_from_component_item(item)  # type: ignore[attr-defined]
            except Exception:
                numbers = []
            if session_index in [int(n) for n in numbers if n]:
                return item
        return None

    def recalculate_student_session_progress(self, *, class_id: str | None, course_id: str, username: str | None = None) -> dict[str, Any]:
        sessions = self.get_session_structure(course_id=course_id, class_id=class_id)
        if not sessions:
            return {'class_id': class_id, 'course_id': course_id, 'processed': 0, 'sessions': 0, 'message': 'Chưa có cấu trúc Bài/Session. Hãy rebuild session structure trước.'}
        users = self._student_usernames_for_class(class_id=class_id, course_id=course_id, username=username)
        self.recalculate_course_quiz_attempts(course_id=course_id, username=username)
        snapshots = self._learning_snapshots_by_username(class_id=class_id, course_id=course_id)
        academic_service = AcademicService(self.db)
        now = datetime.utcnow()
        saved = 0
        for user in users:
            quiz_attempts = self._quiz_attempts_for_user(course_id=course_id, username=user)
            video_rows = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.course_id == course_id, AnalyticsStudentVideoProgress.username == user).all()
            videos_by_session: dict[int, list[AnalyticsStudentVideoProgress]] = defaultdict(list)
            for row in video_rows:
                if row.session_index:
                    videos_by_session[int(row.session_index)].append(row)
            components = []
            snapshot = snapshots.get(user)
            if snapshot:
                try:
                    components = academic_service._component_scores_from_snapshot(snapshot)  # type: ignore[attr-defined]
                except Exception:
                    components = []
            for session in sessions:
                session_index = int(session.get('session_index') or 0)
                if session_index <= 0:
                    continue
                rows = videos_by_session.get(session_index, [])
                session_type = str(session.get('session_type') or 'LEARNING_SESSION')
                quiz_item = self._quiz_item_for_session(components=components, session_index=session_index, academic_service=academic_service)
                raw_attempt = self._quiz_attempt_for_session(attempts=quiz_attempts, session=session)
                quiz_score = None
                quiz_attempted = False
                quiz_completed = False
                quiz_submitted_at = None
                if raw_attempt:
                    quiz_attempted = bool((raw_attempt.submission_count or 0) > 0 or raw_attempt.started_at)
                    quiz_completed = bool((raw_attempt.submission_count or 0) > 0)
                    quiz_submitted_at = raw_attempt.first_submission_at
                    if raw_attempt.score_possible and raw_attempt.score_possible > 0 and raw_attempt.score_earned is not None:
                        quiz_score = round((float(raw_attempt.score_earned) / float(raw_attempt.score_possible)) * 10.0, 2)
                if quiz_item and not raw_attempt:
                    try:
                        score_percent = academic_service._component_score_percent(quiz_item)  # type: ignore[attr-defined]
                    except Exception:
                        score_percent = None
                    quiz_score = round(score_percent / 10.0, 2) if score_percent is not None else None
                    quiz_attempted = score_percent is not None or bool(quiz_item.get('submitted_at'))
                    quiz_completed = bool(score_percent is not None and score_percent >= 100)
                    quiz_submitted_at = self._as_datetime(quiz_item.get('submitted_at'))
                first_video_at = min([r.first_played_at for r in rows if r.first_played_at] or [None])
                last_video_at = max([r.last_event_at for r in rows if r.last_event_at] or [None])
                last_activity_at = max([d for d in [last_video_at, quiz_submitted_at] if d] or [None])
                started_at = min([d for d in [first_video_at, quiz_submitted_at] if d] or [None])
                deadline_at = self._as_datetime(session.get('deadline_at'))
                total_videos = int(session.get('total_videos') or 0)
                videos_seen = len(rows)
                videos_completed = len([r for r in rows if r.is_completed])
                avg_completion = round(sum([r.completion_percent or 0 for r in rows]) / len(rows), 2) if rows else None
                watch_seconds = float(sum([r.estimated_watch_seconds or 0 for r in rows]))
                avg_video_quality = round(sum([r.video_quality_percent or 0 for r in rows]) / len(rows), 2) if rows else None
                passive_watch_seconds = float(sum([r.passive_watch_seconds or 0 for r in rows]))
                long_passive_video_count = len([r for r in rows if (r.long_passive_segment_count or 0) > 0])
                reason_codes: list[str] = []
                if not deadline_at:
                    reason_codes.append('MISSING_DEADLINE_MAPPING')
                if quiz_submitted_at and first_video_at and quiz_submitted_at < first_video_at:
                    reason_codes.append('QUIZ_BEFORE_VIDEO')
                if raw_attempt and raw_attempt.suspicious_quiz_speed:
                    reason_codes.append('SUSPICIOUS_QUIZ_SPEED')
                if raw_attempt and raw_attempt.fishing_pattern:
                    reason_codes.append('FISHING_PATTERN')
                if raw_attempt and (raw_attempt.showanswer_count or 0) > 0:
                    reason_codes.append('SHOWANSWER_USED_NEUTRAL')
                if any(r.is_suspicious for r in rows):
                    reason_codes.extend([code for r in rows for code in str(r.suspicious_reason or '').split(',') if code])
                completed_before_deadline: bool | None = None
                completed_late: bool | None = None
                low_video_quality = bool(avg_video_quality is not None and avg_video_quality < 35)
                if session_type != 'LEARNING_SESSION':
                    reason_codes.append(f'SESSION_TYPE_{session_type}')
                enough_video = total_videos <= 0 or (videos_completed >= total_videos)
                likely_done = enough_video and (quiz_completed or quiz_attempted or videos_completed > 0)
                if likely_done and deadline_at and last_activity_at:
                    completed_before_deadline = last_activity_at <= deadline_at
                    completed_late = last_activity_at > deadline_at
                    if completed_late:
                        reason_codes.append('COMPLETED_LATE')
                    else:
                        reason_codes.append('DEADLINE_PATTERN_MATCHED')
                status = 'INSUFFICIENT_DATA'
                if not started_at:
                    status = 'NOT_STARTED'
                elif 'QUIZ_BEFORE_VIDEO' in reason_codes or any(code in reason_codes for code in ('HIGH_COMPLETION_LOW_WATCH_TIME', 'LARGE_SEEK_JUMP', 'SUSPICIOUS_QUIZ_SPEED', 'FISHING_PATTERN')):
                    status = 'POSSIBLE_SUSPICIOUS'
                elif completed_late:
                    status = 'COMPLETED_LATE'
                elif likely_done:
                    status = 'LIKELY_COMPLETED'
                elif videos_seen > 0:
                    status = 'IN_PROGRESS'
                row = self.db.query(AnalyticsStudentSessionProgress).filter(
                    AnalyticsStudentSessionProgress.course_id == course_id,
                    AnalyticsStudentSessionProgress.username == user,
                    AnalyticsStudentSessionProgress.session_index == session_index,
                ).first()
                if not row:
                    row = AnalyticsStudentSessionProgress(course_id=course_id, username=user, session_key=session.get('session_key') or f'{course_id}:session:{session_index}', session_index=session_index)
                    self.db.add(row)
                row.user_id = snapshot.raw_json.get('user_id') if snapshot and isinstance(snapshot.raw_json, dict) else row.user_id
                row.session_key = session.get('session_key') or row.session_key
                row.session_title = session.get('session_title') or f'Bài {session_index}'
                row.week_index = session.get('week_index')
                row.deadline_at = deadline_at
                row.deadline_source = session.get('deadline_source') or 'INFERRED'
                row.session_type = session_type
                row.total_videos = total_videos
                row.videos_seen = videos_seen
                row.videos_completed = videos_completed
                row.avg_video_completion_percent = avg_completion
                row.avg_video_quality_percent = avg_video_quality
                row.estimated_watch_seconds = watch_seconds
                row.passive_watch_seconds = passive_watch_seconds
                row.long_passive_video_count = long_passive_video_count
                row.quiz_attempted = quiz_attempted
                row.quiz_completed = quiz_completed
                row.quiz_score = quiz_score
                row.started_at = started_at
                row.last_activity_at = last_activity_at
                row.completed_before_deadline = completed_before_deadline
                row.completed_late = completed_late
                row.session_learning_status = status
                row.reason_codes = sorted(set(reason_codes))
                row.evidence_json = {
                    'deadline_source': session.get('deadline_source'),
                    'deadline_mapping_quality': session.get('deadline_mapping_quality'),
                    'quiz_deadline_configured': session.get('quiz_deadline_configured'),
                    'quiz_submitted_at': quiz_submitted_at.isoformat() if quiz_submitted_at else None,
                    'quiz_usage_key': session.get('quiz_usage_key'),
                    'raw_quiz_attempt_id': raw_attempt.id if raw_attempt else None,
                    'session_type': session_type,
                    'avg_video_quality_percent': avg_video_quality,
                    'passive_watch_seconds': passive_watch_seconds,
                    'long_passive_video_count': long_passive_video_count,
                    'crammed_low_watch_candidate': low_video_quality,
                    'video_count': len(rows),
                }
                row.calculated_at = now
                saved += 1
        self.db.commit()
        return {'class_id': class_id, 'course_id': course_id, 'processed': len(users), 'sessions': len(sessions), 'session_progress_rows': saved}

    def recalculate_learning_behavior(self, *, class_id: str | None, course_id: str, username: str | None = None) -> dict[str, Any]:
        self.recalculate_student_session_progress(class_id=class_id, course_id=course_id, username=username)
        users = self._student_usernames_for_class(class_id=class_id, course_id=course_id, username=username)
        if not users and username:
            users = [username]

        events_by_user = self._events_count_by_username(course_id=course_id, usernames=users)
        videos_by_user = self._video_progress_by_username(course_id=course_id, usernames=users)
        sessions_by_user = self._session_progress_by_username(course_id=course_id, usernames=users)

        now = datetime.utcnow()
        counts = Counter()
        for user in users:
            rows = videos_by_user.get(user, [])
            events_count = events_by_user.get(user, 0)
            session_rows = sessions_by_user.get(user, [])
            learning_session_rows = [r for r in session_rows if (getattr(r, 'session_type', 'LEARNING_SESSION') or 'LEARNING_SESSION') == 'LEARNING_SESSION']
            completed = [r for r in rows if r.is_completed]
            suspicious = [r for r in rows if r.is_suspicious]
            avg_completion = round(sum((r.completion_percent or 0) for r in rows) / len(rows), 2) if rows else None
            avg_watch = round(sum((r.estimated_watch_percent or 0) for r in rows) / len(rows), 2) if rows else None
            quality_values = [r.video_quality_percent for r in rows if r.video_quality_percent is not None]
            avg_quality = round(sum(float(v or 0) for v in quality_values) / len(quality_values), 2) if quality_values else None
            deadline_known = [r for r in learning_session_rows if r.deadline_at]
            on_time = len([r for r in learning_session_rows if r.completed_before_deadline is True])
            late = len([r for r in learning_session_rows if r.completed_late is True])
            quiz_before = len([r for r in learning_session_rows if 'QUIZ_BEFORE_VIDEO' in (r.reason_codes or [])])
            suspicious_quiz_speed = len([r for r in learning_session_rows if 'SUSPICIOUS_QUIZ_SPEED' in (r.reason_codes or [])])
            fishing_pattern = len([r for r in learning_session_rows if 'FISHING_PATTERN' in (r.reason_codes or [])])
            late_completion_dates = [r.last_activity_at.date() for r in learning_session_rows if r.last_activity_at and r.completed_late]
            crammed = max(Counter(late_completion_dates).values()) if late_completion_dates else 0
            crammed = crammed if crammed >= 3 else 0
            crammed_low_watch = 0
            if crammed:
                for dt, count in Counter(late_completion_dates).items():
                    if count >= 3:
                        crammed_low_watch += len([r for r in learning_session_rows if r.last_activity_at and r.last_activity_at.date() == dt and (r.evidence_json or {}).get('crammed_low_watch_candidate')])
            total_watch_seconds = sum((r.estimated_watch_seconds or 0) for r in rows)
            passive_watch_seconds = sum((r.passive_watch_seconds or 0) for r in rows)
            watch_without_quiz = len([r for r in learning_session_rows if (r.estimated_watch_seconds or 0) > 60 and not r.quiz_attempted])
            watch_without_navigation = len([r for r in learning_session_rows if (r.passive_watch_seconds or 0) > 0 or (r.long_passive_video_count or 0) > 0])
            inp = BehaviorInput(
                total_events=events_count,
                total_sessions=len(learning_session_rows) or len({r.session_index for r in rows if r.session_index}) or 0,
                sessions_started=len([r for r in learning_session_rows if r.started_at]) or len({r.session_index for r in rows if r.session_index}) or (1 if rows else 0),
                sessions_completed_on_time=on_time,
                sessions_completed_late=late,
                crammed_session_count=crammed,
                crammed_low_watch_session_count=crammed_low_watch,
                quiz_before_video_count=quiz_before,
                video_before_quiz_count=len([r for r in learning_session_rows if r.quiz_attempted and 'QUIZ_BEFORE_VIDEO' not in (r.reason_codes or [])]),
                total_quiz_sessions=len([r for r in learning_session_rows if r.quiz_attempted]),
                total_quiz_attempts=len([r for r in learning_session_rows if r.quiz_attempted]),
                suspicious_quiz_speed_count=suspicious_quiz_speed,
                fishing_pattern_count=fishing_pattern,
                total_videos_seen=len(rows),
                total_videos_completed=len(completed),
                avg_video_completion_percent=avg_completion,
                total_estimated_watch_seconds=total_watch_seconds,
                avg_estimated_watch_percent=avg_watch,
                avg_video_quality_percent=avg_quality,
                suspicious_video_count=len(suspicious),
                long_passive_video_count=len([r for r in rows if (r.long_passive_segment_count or 0) > 0]),
                passive_watch_seconds=passive_watch_seconds,
                watch_without_quiz_session_count=watch_without_quiz,
                watch_without_navigation_session_count=watch_without_navigation,
                missing_duration_count=len([r for r in rows if not r.duration_seconds]),
                missing_session_mapping=any(r.session_index is None for r in rows) if rows else bool(not learning_session_rows),
                missing_deadline_mapping=bool(learning_session_rows and len(deadline_known) < len(learning_session_rows)),
                last_activity_at=max([d for d in [r.last_activity_at for r in learning_session_rows] + [r.last_event_at for r in rows] if d] or [None]),
                extra_reasons=[code for r in suspicious for code in (r.suspicious_reason or '').split(',') if code] + [code for sr in learning_session_rows for code in (sr.reason_codes or []) if code],
            )
            result = classify_learning_behavior(inp)
            snap = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(
                AnalyticsLearningBehaviorSnapshot.class_id == class_id,
                AnalyticsLearningBehaviorSnapshot.course_id == course_id,
                AnalyticsLearningBehaviorSnapshot.username == user,
            ).first()
            if not snap:
                snap = AnalyticsLearningBehaviorSnapshot(class_id=class_id, course_id=course_id, username=user)
                self.db.add(snap)
            snap.classification = result.classification
            snap.display_label = self._safe_label(result.classification, result.display_label)
            snap.confidence_score = result.confidence_score
            snap.real_learning_score = result.real_learning_score
            snap.idle_score = result.idle_score
            snap.suspicious_score = result.suspicious_score
            snap.deadline_compliance_percent = round((on_time / len(deadline_known)) * 100, 2) if deadline_known else None
            snap.crammed_session_count = int(crammed)
            snap.quiz_before_video_count = int(quiz_before)
            snap.reason_codes = result.reason_codes
            snap.human_readable_summary = result.human_readable_summary
            snap.recommended_action = result.recommended_action
            snap.data_quality = result.data_quality
            snap.evidence_json = {**result.evidence, 'deadline_known_sessions': len(deadline_known), 'on_time_sessions': on_time, 'late_sessions': late, 'quiz_before_video_count': quiz_before, 'learning_session_count': len(learning_session_rows), 'session_types_excluded': len(session_rows) - len(learning_session_rows)}
            snap.last_activity_at = inp.last_activity_at
            snap.calculated_at = now
            counts[result.classification] += 1
        self.db.commit()
        return {'class_id': class_id, 'course_id': course_id, 'processed': len(users), 'counts': dict(counts)}



    @staticmethod
    def _safe_label(classification: str | None, display_label: str | None = None) -> str:
        value = str(classification or '').upper()
        mapping = {
            'LIKELY_REAL_LEARNING': 'Có dấu hiệu học thật',
            'POSSIBLE_IDLE': 'Có khả năng treo máy',
            'POSSIBLE_ANOMALY': 'Dấu hiệu bất thường cần kiểm tra',
            'POSSIBLE_CHEATING': 'Dấu hiệu bất thường cần kiểm tra',
            'INSUFFICIENT_DATA': 'Chưa đủ dữ liệu',
            'NORMAL': 'Chưa thấy bất thường rõ',
        }
        return mapping.get(value) or display_label or 'Chưa đủ dữ liệu'

    @staticmethod
    def _recommended_action_label(value: str | None) -> str:
        action = str(value or '').upper()
        mapping = {
            'NO_ACTION': 'Không cần xử lý',
            'REMIND_STUDENT': 'Nhắc sinh viên xác nhận tiến độ học',
            'TEACHER_REVIEW': 'Giáo viên xem lại trước khi xử lý',
            'CHECK_WITH_STUDENT': 'Trao đổi thêm với sinh viên',
            'REQUIRE_ADDITIONAL_ACTIVITY': 'Yêu cầu sinh viên học bổ sung',
            'INSUFFICIENT_DATA_RECHECK_LATER': 'Kiểm tra lại sau khi có thêm dữ liệu',
        }
        return mapping.get(action, 'Kiểm tra lại sau khi có thêm dữ liệu')

    @staticmethod
    def _parse_datetime_filter(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            return None


    @staticmethod
    def _csv_setting_set(value: Any) -> set[str]:
        if not value:
            return set()
        if isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = str(value).replace(';', ',').split(',')
        return {str(part).strip().lower() for part in parts if str(part).strip()}

    def _class_matches_rollout(self, cls: AcademicClass | None, course_id: str | None = None) -> tuple[bool, list[str]]:
        """Check env-only rollout scope; does not require new tables."""
        reasons: list[str] = []
        if not bool(getattr(settings, 'analytics_rollout_enabled', True)):
            return False, ['ROLLOUT_DISABLED']
        mode = str(getattr(settings, 'analytics_rollout_mode', 'pilot') or 'pilot').strip().lower()
        if mode == 'off':
            return False, ['ROLLOUT_MODE_OFF']
        campuses = self._csv_setting_set(getattr(settings, 'analytics_rollout_campuses', ''))
        branches = self._csv_setting_set(getattr(settings, 'analytics_rollout_branches', ''))
        class_ids = self._csv_setting_set(getattr(settings, 'analytics_rollout_class_ids', ''))
        course_ids = self._csv_setting_set(getattr(settings, 'analytics_rollout_course_ids', ''))
        # Empty scope means "all visible classes". In pilot mode admins can narrow
        # by env vars without schema changes.
        if cls is not None:
            if campuses and str(cls.campus or '').strip().lower() not in campuses:
                reasons.append('CAMPUS_NOT_IN_ROLLOUT')
            if branches and str(cls.branch or '').strip().lower() not in branches:
                reasons.append('BRANCH_NOT_IN_ROLLOUT')
            if class_ids and str(cls.id or '').strip().lower() not in class_ids and str(cls.class_code or '').strip().lower() not in class_ids:
                reasons.append('CLASS_NOT_IN_ROLLOUT')
        elif class_ids:
            reasons.append('CLASS_SCOPE_REQUIRED')
        if course_ids and course_id and str(course_id).strip().lower() not in course_ids:
            reasons.append('COURSE_NOT_IN_ROLLOUT')
        return not reasons, reasons

    def rollout_control_report(
        self,
        *,
        campus: str | None = None,
        branch: str | None = None,
        class_id: str | None = None,
        course_id: str | None = None,
        allowed_class_ids: set[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Env-only rollout controls for moving from pilot to production.

        Uses AcademicClass/course mapping and existing RBAC scope. No rollout table
        is created: production can start with env allowlists and later promote to
        full scope by changing ANALYTICS_ROLLOUT_MODE/SCOPES.
        """
        mode = str(getattr(settings, 'analytics_rollout_mode', 'pilot') or 'pilot').strip().lower()
        enabled = bool(getattr(settings, 'analytics_rollout_enabled', True)) and mode != 'off'
        q = self.db.query(AcademicClass).filter(AcademicClass.active.is_(True))
        if class_id:
            q = q.filter(AcademicClass.id == class_id)
        if campus:
            q = q.filter(AcademicClass.campus == campus)
        if branch:
            q = q.filter(AcademicClass.branch == branch)
        if allowed_class_ids is not None:
            q = q.filter(AcademicClass.id.in_(sorted(allowed_class_ids))) if allowed_class_ids else q.filter(False)
        classes = q.order_by(AcademicClass.updated_at.desc()).limit(min(max(1, limit), 500)).all()
        items: list[dict[str, Any]] = []
        counters = Counter()
        for cls in classes:
            mapped_course_id = self._course_for_class(cls.id, course_id)
            in_rollout, reasons = self._class_matches_rollout(cls, mapped_course_id)
            behavior_count = self.db.query(AnalyticsLearningBehaviorSnapshot.id).filter(
                AnalyticsLearningBehaviorSnapshot.class_id == cls.id,
                AnalyticsLearningBehaviorSnapshot.course_id == mapped_course_id,
            ).count() if mapped_course_id else 0
            student_count = self.db.query(AcademicClassStudent.id).filter(AcademicClassStudent.class_id == cls.id).count()
            session_count = self.db.query(AnalyticsCourseSession.id).filter(AnalyticsCourseSession.course_id == mapped_course_id, AnalyticsCourseSession.active.is_(True)).count() if mapped_course_id else 0
            if in_rollout:
                counters['in_rollout'] += 1
            else:
                counters['out_of_rollout'] += 1
            if behavior_count > 0:
                counters['has_snapshot'] += 1
            if session_count <= 0:
                counters['missing_session_structure'] += 1
            if not mapped_course_id:
                counters['missing_course_mapping'] += 1
            items.append({
                'class_id': cls.id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'course_id': mapped_course_id,
                'student_count': int(student_count or 0),
                'session_count': int(session_count or 0),
                'behavior_snapshot_count': int(behavior_count or 0),
                'in_rollout': bool(enabled and in_rollout),
                'rollout_reasons': reasons,
                'recommended_action': 'Có thể dùng trong phạm vi rollout.' if enabled and in_rollout else 'Chưa nằm trong phạm vi rollout hoặc rollout đang tắt.',
            })
        blockers: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        if not enabled:
            blockers.append({'code': 'ROLLOUT_DISABLED', 'message': 'Học online analytics đang tắt rollout.', 'action': 'Bật ANALYTICS_ROLLOUT_ENABLED=true và ANALYTICS_ROLLOUT_MODE=production/production.'})
        if enabled and not any(item.get('in_rollout') for item in items):
            warnings.append({'code': 'NO_CLASS_IN_ROLLOUT_SCOPE', 'message': 'Không có lớp nào trong phạm vi rollout hiện tại.', 'action': 'Kiểm tra allowlist campus/class/course hoặc bộ lọc.'})
        if mode == 'production' and (counters.get('missing_course_mapping') or counters.get('missing_session_structure')):
            warnings.append({'code': 'ROLLOUT_SCOPE_HAS_INCOMPLETE_MAPPING', 'message': 'Một số lớp trong phạm vi rollout còn thiếu mapping course/session.', 'action': 'Backfill/rebuild trước khi mở rộng toàn kỳ.'})
        rollout_status = 'DISABLED' if not enabled else ('READY' if not blockers and not warnings else 'READY_WITH_WARNINGS')
        return {
            'version': '25.9.16.7.2.7',
            'rollout_status': rollout_status,
            'enabled': enabled,
            'mode': mode.upper(),
            'allow_backfill': bool(getattr(settings, 'analytics_rollout_allow_backfill', True)),
            'allow_export': bool(getattr(settings, 'analytics_rollout_allow_export', True)),
            'scope': {
                'campuses': sorted(self._csv_setting_set(getattr(settings, 'analytics_rollout_campuses', ''))),
                'branches': sorted(self._csv_setting_set(getattr(settings, 'analytics_rollout_branches', ''))),
                'class_ids': sorted(self._csv_setting_set(getattr(settings, 'analytics_rollout_class_ids', ''))),
                'course_ids': sorted(self._csv_setting_set(getattr(settings, 'analytics_rollout_course_ids', ''))),
            },
            'filters': {'campus': campus, 'branch': branch, 'class_id': class_id, 'course_id': course_id, 'limit': limit},
            'counters': dict(counters),
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'issues': blockers + warnings,
            'items': items,
            'next_actions': [i.get('action') for i in blockers + warnings if i.get('action')],
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'Rollout chỉ bật/tắt phạm vi hiển thị và job học online; nhận định vẫn là tín hiệu mềm, không phải kết luận vi phạm.',
        }

    def analytics_monitoring_report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Read-only monitoring for scheduler, stuck jobs and stale snapshots."""
        ingest = self.ingest_status()
        now = datetime.utcnow()
        stale_ingest_seconds = int(getattr(settings, 'analytics_monitoring_stale_ingest_seconds', 900) or 900)
        stuck_job_minutes = int(getattr(settings, 'analytics_monitoring_stuck_job_minutes', 60) or 60)
        snapshot_stale_hours = int(getattr(settings, 'analytics_monitoring_snapshot_stale_hours', getattr(settings, 'analytics_snapshot_stale_hours', 168)) or 168)
        warning_active_jobs = int(getattr(settings, 'analytics_monitoring_warning_active_jobs', 10) or 10)
        issues: list[dict[str, str]] = []

        last_run_at = self._parse_datetime_filter(ingest.get('last_run_at'))
        seconds_since_ingest = None
        if last_run_at:
            seconds_since_ingest = max(0, int((now - last_run_at).total_seconds()))
        if not bool(getattr(settings, 'analytics_ingest_scheduler_enabled', False)):
            issues.append({'severity': 'warning', 'code': 'SCHEDULER_DISABLED', 'message': 'Scheduler ingest học online đang tắt.', 'action': 'Bật ANALYTICS_INGEST_SCHEDULER_ENABLED=true hoặc chạy ingest theo cron ngoài.'})
        if last_run_at and seconds_since_ingest is not None and seconds_since_ingest > stale_ingest_seconds:
            issues.append({'severity': 'warning', 'code': 'INGEST_STALE', 'message': 'Ingest tracking log đã lâu chưa chạy.', 'action': 'Kiểm tra worker/scheduler hoặc chạy ingest thủ công.'})
        if not ingest.get('file_exists'):
            issues.append({'severity': 'blocker', 'code': 'TRACKING_LOG_NOT_MOUNTED', 'message': 'Không thấy tracking.log trong container.', 'action': 'Kiểm tra mount read-only Tutor logs.'})

        active_q = self.db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.job_type.in_(['learning_analytics_recalculate']),
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        )
        if class_id:
            active_q = active_q.filter(AcademicClassSyncJob.class_id == class_id)
        elif allowed_class_ids is not None:
            active_q = active_q.filter(AcademicClassSyncJob.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else active_q.filter(False)
        active_jobs = active_q.count()
        stuck_cutoff = now - timedelta(minutes=stuck_job_minutes)
        stuck_jobs = active_q.filter(AcademicClassSyncJob.created_at <= stuck_cutoff).limit(20).all()
        if active_jobs > warning_active_jobs:
            issues.append({'severity': 'warning', 'code': 'MANY_ACTIVE_ANALYTICS_JOBS', 'message': 'Đang có nhiều job học online active.', 'action': 'Chờ job hoàn tất trước khi enqueue thêm.'})
        if stuck_jobs:
            issues.append({'severity': 'blocker', 'code': 'STUCK_ANALYTICS_JOBS', 'message': f'{len(stuck_jobs)} job học online có dấu hiệu treo/quá lâu.', 'action': 'Kiểm tra worker logs, Redis/Celery và xử lý job treo trong /jobs.'})

        behavior_q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if class_id:
            behavior_q = behavior_q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        elif allowed_class_ids is not None:
            behavior_q = behavior_q.filter(AnalyticsLearningBehaviorSnapshot.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else behavior_q.filter(False)
        if course_id:
            behavior_q = behavior_q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)
        snapshot_count = behavior_q.count()
        stale_cutoff = now - timedelta(hours=snapshot_stale_hours)
        stale_snapshot_count = behavior_q.filter(AnalyticsLearningBehaviorSnapshot.calculated_at < stale_cutoff).count() if snapshot_count else 0
        latest = behavior_q.order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first()
        if snapshot_count <= 0:
            issues.append({'severity': 'warning', 'code': 'NO_BEHAVIOR_SNAPSHOT', 'message': 'Chưa có snapshot học online trong phạm vi này.', 'action': 'Chạy backfill/tính lại học online.'})
        elif stale_snapshot_count > 0:
            issues.append({'severity': 'warning', 'code': 'STALE_BEHAVIOR_SNAPSHOTS', 'message': f'{stale_snapshot_count} snapshot học online đã cũ.', 'action': 'Backfill lại các lớp stale trước khi báo cáo production.'})

        blocker_count = len([i for i in issues if i.get('severity') == 'blocker'])
        warning_count = len([i for i in issues if i.get('severity') == 'warning'])
        monitoring_status = 'BLOCKED' if blocker_count else ('WARNING' if warning_count else 'OK')
        return {
            'version': '25.9.16.7.2.7',
            'monitoring_status': monitoring_status,
            'ready_for_rollout': monitoring_status in {'OK', 'WARNING'} and bool(getattr(settings, 'analytics_rollout_enabled', True)),
            'scheduler_enabled': bool(getattr(settings, 'analytics_ingest_scheduler_enabled', False)),
            'seconds_since_last_ingest': seconds_since_ingest,
            'active_analytics_jobs': int(active_jobs or 0),
            'stuck_analytics_job_count': len(stuck_jobs),
            'stuck_jobs': [{'id': j.id, 'class_id': j.class_id, 'status': j.status, 'created_at': j.created_at.isoformat() if j.created_at else None, 'progress_label': j.progress_label} for j in stuck_jobs],
            'snapshot_count': int(snapshot_count or 0),
            'stale_snapshot_count': int(stale_snapshot_count or 0),
            'latest_behavior_calculated_at': latest.calculated_at.isoformat() if latest and latest.calculated_at else None,
            'ingest': ingest,
            'issue_count': len(issues),
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'issues': issues,
            'next_actions': [i.get('action') for i in issues if i.get('action')],
            'safe_policy': 'signals_only_not_violation',
        }



    def analytics_data_quality_report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Production readiness guard for Aspects-lite analytics.

        This method reads only checkpoint/snapshot/aggregate tables. It never
        scans tracking.log and is safe for dashboards, health checks and smoke
        tests. The result is deliberately operational: it tells admins what is
        missing before they trust the soft learning-behavior signals.
        """
        ingest = self.ingest_status()
        resolved_course_id = self._course_for_class(class_id, course_id)
        issues: list[dict[str, Any]] = []
        now = datetime.utcnow()

        if class_id and allowed_class_ids is not None and class_id not in allowed_class_ids:
            return {
                'status': 'FORBIDDEN',
                'readiness': 'NO_SCOPE',
                'message': 'Bạn không có quyền xem chất lượng dữ liệu học online của lớp này.',
                'issues': [{'severity': 'error', 'code': 'NO_CLASS_SCOPE', 'message': 'Không có quyền truy cập lớp.', 'action': 'Kiểm tra lại phân quyền.'}],
                'safe_policy': 'signals_only_not_violation',
            }

        if not ingest.get('enabled'):
            issues.append({'severity': 'error', 'code': 'INGEST_DISABLED', 'message': 'Analytics ingest đang tắt.', 'action': 'Bật ANALYTICS_INGEST_ENABLED=true rồi chạy ingest.'})
        if not ingest.get('file_exists'):
            issues.append({'severity': 'error', 'code': 'TRACKING_LOG_NOT_MOUNTED', 'message': 'Chưa thấy tracking.log trong container AI Server.', 'action': 'Mount thư mục Tutor LMS logs dạng read-only vào /openedx-data/lms/logs.'})
        if int(ingest.get('total_events_inserted') or 0) <= 0:
            issues.append({'severity': 'warning', 'code': 'NO_TRACKING_EVENTS_INGESTED', 'message': 'Chưa có event tracking nào được ingest.', 'action': 'Chạy ingest thủ công hoặc bật scheduler ingest.'})
        if int(ingest.get('total_parse_errors') or 0) > max(50, int(ingest.get('total_events_inserted') or 0) * 0.1):
            issues.append({'severity': 'warning', 'code': 'HIGH_PARSE_ERROR_COUNT', 'message': 'Số dòng tracking log parse lỗi đang cao.', 'action': 'Kiểm tra format log/prefix logger.py và event JSON string.'})

        class_count = 0
        student_count = 0
        behavior_count = 0
        session_count = 0
        video_progress_count = 0
        session_progress_count = 0
        latest_behavior_at = None
        deadline_sources: dict[str, int] = {}
        missing_duration_count = 0
        stale_hours = int(getattr(settings, 'analytics_snapshot_stale_hours', 168) or 168)

        if class_id:
            class_count = 1 if self.db.get(AcademicClass, class_id) else 0
            if class_count <= 0:
                issues.append({'severity': 'error', 'code': 'CLASS_NOT_FOUND', 'message': 'Không tìm thấy lớp trong AcademicClass.', 'action': 'Đồng bộ lại dữ liệu AP/CMS cho lớp.'})
            student_count = self.db.query(AcademicClassStudent.id).filter(AcademicClassStudent.class_id == class_id).count()
            if student_count <= 0:
                issues.append({'severity': 'warning', 'code': 'NO_CLASS_STUDENTS', 'message': 'Lớp chưa có sinh viên trong hệ thống.', 'action': 'Đồng bộ AP hoặc kiểm tra mapping lớp-sinh viên.'})
            if not resolved_course_id:
                issues.append({'severity': 'error', 'code': 'MISSING_COURSE_MAPPING', 'message': 'Lớp chưa map Course CMS/Open edX.', 'action': 'Map course ở màn Tiến độ học trước khi tính học online.'})
        else:
            q = self.db.query(AcademicClass.id).filter(AcademicClass.active.is_(True))
            if allowed_class_ids is not None:
                q = q.filter(AcademicClass.id.in_(sorted(allowed_class_ids))) if allowed_class_ids else q.filter(False)
            class_count = q.count()

        if resolved_course_id:
            session_count = self.db.query(AnalyticsCourseSession.id).filter(AnalyticsCourseSession.course_id == resolved_course_id, AnalyticsCourseSession.active.is_(True)).count()
            if session_count <= 0:
                issues.append({'severity': 'error', 'code': 'MISSING_SESSION_STRUCTURE', 'message': 'Chưa có mapping Bài/Session → video → quiz cho course.', 'action': 'Rebuild session structure từ course blocks trước khi recalculate.'})
            rows = self.db.query(AnalyticsCourseSession.deadline_source, func.count(AnalyticsCourseSession.id)).filter(AnalyticsCourseSession.course_id == resolved_course_id, AnalyticsCourseSession.active.is_(True)).group_by(AnalyticsCourseSession.deadline_source).all()
            deadline_sources = {str(k or 'UNKNOWN'): int(v or 0) for k, v in rows}
            if session_count > 0 and not any(k in deadline_sources for k in ('QUIZ_DEADLINE', 'MANUAL', 'SEMESTER', 'OFFICIAL')):
                issues.append({'severity': 'warning', 'code': 'INFERRED_DEADLINE_ONLY', 'message': 'Deadline đang chủ yếu là suy luận 6 tuần.', 'action': 'Ưu tiên dùng deadline Quiz đã cấu hình hoặc /semesters nếu có.'})
            missing_duration_count = self.db.query(AnalyticsStudentVideoProgress.id).filter(
                AnalyticsStudentVideoProgress.course_id == resolved_course_id,
                (AnalyticsStudentVideoProgress.duration_seconds.is_(None)) | (AnalyticsStudentVideoProgress.duration_seconds <= 0),
            ).count()
            if missing_duration_count > 0:
                issues.append({'severity': 'warning', 'code': 'MISSING_VIDEO_DURATION', 'message': f'{missing_duration_count} video progress thiếu duration.', 'action': 'Kiểm tra event duration trong tracking log hoặc course block video metadata.'})
            video_progress_count = self.db.query(AnalyticsStudentVideoProgress.id).filter(AnalyticsStudentVideoProgress.course_id == resolved_course_id).count()
            session_progress_count = self.db.query(AnalyticsStudentSessionProgress.id).filter(AnalyticsStudentSessionProgress.course_id == resolved_course_id).count()
            if video_progress_count <= 0 and int(ingest.get('total_events_inserted') or 0) > 0:
                issues.append({'severity': 'warning', 'code': 'NO_VIDEO_PROGRESS_SNAPSHOT', 'message': 'Đã có tracking events nhưng chưa có snapshot video progress.', 'action': 'Chạy tính lại học online cho course/lớp.'})
        if class_id and resolved_course_id:
            behavior_q = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(
                AnalyticsLearningBehaviorSnapshot.class_id == class_id,
                AnalyticsLearningBehaviorSnapshot.course_id == resolved_course_id,
            )
            behavior_count = behavior_q.count()
            latest = behavior_q.order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first()
            latest_behavior_at = latest.calculated_at if latest else None
            if student_count > 0 and behavior_count <= 0:
                issues.append({'severity': 'warning', 'code': 'NO_BEHAVIOR_SNAPSHOT', 'message': 'Lớp chưa có nhận định học online.', 'action': 'Bấm Tính lại học online hoặc chạy backfill job.'})
            if latest_behavior_at and (now - latest_behavior_at) > timedelta(hours=stale_hours):
                issues.append({'severity': 'warning', 'code': 'STALE_BEHAVIOR_SNAPSHOT', 'message': f'Snapshot học online cũ hơn {stale_hours} giờ.', 'action': 'Chạy lại học online cho lớp để cập nhật dữ liệu mới.'})
        elif not class_id:
            behavior_count = self.db.query(AnalyticsLearningBehaviorSnapshot.id).count()
            latest = self.db.query(AnalyticsLearningBehaviorSnapshot).order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first()
            latest_behavior_at = latest.calculated_at if latest else None
            if behavior_count <= 0:
                issues.append({'severity': 'warning', 'code': 'NO_GLOBAL_BEHAVIOR_SNAPSHOT', 'message': 'Chưa có snapshot nhận định học online nào.', 'action': 'Chạy backfill theo lớp/kỳ sau khi ingest log.'})

        error_count = len([i for i in issues if i.get('severity') == 'error'])
        warning_count = len([i for i in issues if i.get('severity') == 'warning'])
        if error_count:
            readiness = 'CONFIG_NEEDED'
        elif warning_count:
            readiness = 'NEEDS_BACKFILL'
        else:
            readiness = 'READY'

        return {
            'status': 'ok',
            'version': '25.9.16.7.2.7',
            'readiness': readiness,
            'class_id': class_id,
            'course_id': resolved_course_id,
            'counts': {
                'class_count': int(class_count or 0),
                'student_count': int(student_count or 0),
                'session_count': int(session_count or 0),
                'tracking_events_inserted': int(ingest.get('total_events_inserted') or 0),
                'video_progress_count': int(video_progress_count or 0),
                'session_progress_count': int(session_progress_count or 0),
                'behavior_snapshot_count': int(behavior_count or 0),
                'missing_duration_count': int(missing_duration_count or 0),
            },
            'deadline_sources': deadline_sources,
            'latest_behavior_calculated_at': latest_behavior_at.isoformat() if latest_behavior_at else None,
            'ingest': ingest,
            'issues': issues,
            'next_actions': [i.get('action') for i in issues if i.get('action')],
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.',
        }

    def analytics_backfill_plan(
        self,
        *,
        campus: str | None = None,
        branch: str | None = None,
        class_id: str | None = None,
        course_id: str | None = None,
        limit: int = 50,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Plan class-level analytics backfill without enqueuing work."""
        q = self.db.query(AcademicClass).filter(AcademicClass.active.is_(True))
        if class_id:
            q = q.filter(AcademicClass.id == class_id)
        if campus:
            q = q.filter(AcademicClass.campus == campus)
        if branch:
            q = q.filter(AcademicClass.branch == branch)
        if allowed_class_ids is not None:
            q = q.filter(AcademicClass.id.in_(sorted(allowed_class_ids))) if allowed_class_ids else q.filter(False)
        classes = q.order_by(AcademicClass.updated_at.desc()).limit(min(max(1, limit), 200)).all()
        items: list[dict[str, Any]] = []
        counters = Counter()
        for cls in classes:
            mapped_course_id = self._course_for_class(cls.id, course_id)
            student_count = self.db.query(AcademicClassStudent.id).filter(AcademicClassStudent.class_id == cls.id).count()
            session_count = self.db.query(AnalyticsCourseSession.id).filter(AnalyticsCourseSession.course_id == mapped_course_id, AnalyticsCourseSession.active.is_(True)).count() if mapped_course_id else 0
            behavior_count = self.db.query(AnalyticsLearningBehaviorSnapshot.id).filter(AnalyticsLearningBehaviorSnapshot.class_id == cls.id, AnalyticsLearningBehaviorSnapshot.course_id == mapped_course_id).count() if mapped_course_id else 0
            latest = self.db.query(AnalyticsLearningBehaviorSnapshot).filter(AnalyticsLearningBehaviorSnapshot.class_id == cls.id, AnalyticsLearningBehaviorSnapshot.course_id == mapped_course_id).order_by(AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).first() if mapped_course_id else None
            active_job = self.db.query(AcademicClassSyncJob.id).filter(
                AcademicClassSyncJob.class_id == cls.id,
                AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
                AcademicClassSyncJob.status.in_(['queued', 'running']),
            ).first()
            reasons: list[str] = []
            if not mapped_course_id:
                reasons.append('MISSING_COURSE_MAPPING')
            if student_count <= 0:
                reasons.append('NO_CLASS_STUDENTS')
            if mapped_course_id and session_count <= 0:
                # Do not block test-production backfill only because session mapping
                # is missing. Recalculate still creates safe INSUFFICIENT_DATA
                # snapshots for the class, so UI no longer stays at Snapshot=0.
                reasons.append('MISSING_SESSION_STRUCTURE_BUT_CAN_SNAPSHOT_INSUFFICIENT_DATA')
            if mapped_course_id and student_count > 0 and behavior_count < student_count:
                reasons.append('MISSING_OR_PARTIAL_BEHAVIOR_SNAPSHOT')
            if active_job:
                reasons.append('JOB_ALREADY_ACTIVE')
            can_enqueue = bool(mapped_course_id and student_count > 0 and not active_job)
            if can_enqueue:
                counters['enqueueable'] += 1
            if not mapped_course_id:
                counters['missing_course_mapping'] += 1
            if session_count <= 0:
                counters['missing_session_structure'] += 1
            if behavior_count <= 0:
                counters['missing_behavior_snapshot'] += 1
            if active_job:
                counters['active_jobs'] += 1
            items.append({
                'class_id': cls.id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'course_id': mapped_course_id,
                'student_count': int(student_count or 0),
                'session_count': int(session_count or 0),
                'behavior_snapshot_count': int(behavior_count or 0),
                'latest_behavior_calculated_at': latest.calculated_at.isoformat() if latest and latest.calculated_at else None,
                'can_enqueue': can_enqueue,
                'reasons': reasons,
                'recommended_action': 'Tính lại học online' if can_enqueue else 'Kiểm tra mapping/dữ liệu trước khi backfill',
                'safe_note': 'Nếu thiếu Bài/Session, hệ thống vẫn tạo snapshot Chưa đủ dữ liệu để giáo viên không bị màn hình 0 dữ liệu.',
            })
        return {
            'status': 'ok',
            'version': '25.9.16.7.2.7',
            'filters': {'campus': campus, 'branch': branch, 'class_id': class_id, 'course_id': course_id, 'limit': limit},
            'total': len(items),
            'counters': dict(counters),
            'items': items,
            'safe_policy': 'signals_only_not_violation',
        }


    def analytics_enqueue_guard(self, *, class_id: str | None = None, job_type: str = 'learning_analytics_recalculate') -> dict[str, Any]:
        """Production guard before enqueuing expensive analytics work.

        This uses the existing academic_class_sync_jobs table and settings only;
        it does not create a new rate-limit table. The goal is to prevent a user
        from accidentally flooding workers with duplicate class recalculation jobs.
        """
        cooldown_seconds = int(getattr(settings, 'analytics_recalculate_enqueue_cooldown_seconds', 300) or 300)
        max_active = int(getattr(settings, 'analytics_backfill_max_active_jobs', 20) or 20)
        now = datetime.utcnow()
        active_q = self.db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.job_type == job_type,
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        )
        if class_id:
            active_q = active_q.filter(AcademicClassSyncJob.class_id == class_id)
        active_jobs = active_q.count()
        recent = None
        if class_id:
            recent = self.db.query(AcademicClassSyncJob).filter(
                AcademicClassSyncJob.job_type == job_type,
                AcademicClassSyncJob.class_id == class_id,
                AcademicClassSyncJob.created_at >= now - timedelta(seconds=cooldown_seconds),
            ).order_by(AcademicClassSyncJob.created_at.desc()).first()
        allowed = True
        reasons: list[str] = []
        if active_jobs >= max_active and not class_id:
            allowed = False
            reasons.append('TOO_MANY_ACTIVE_ANALYTICS_JOBS')
        if recent:
            allowed = False
            reasons.append('RECENT_ANALYTICS_JOB_EXISTS')
        return {
            'allowed': allowed,
            'job_type': job_type,
            'class_id': class_id,
            'active_jobs': int(active_jobs or 0),
            'max_active_jobs': max_active,
            'cooldown_seconds': cooldown_seconds,
            'recent_job_id': recent.id if recent else None,
            'reasons': reasons,
            'message': 'Có thể đưa vào hàng đợi.' if allowed else 'Đã có job học online đang chạy hoặc vừa được tạo, hãy theo dõi ở /jobs.',
            'safe_policy': 'signals_only_not_violation',
        }

    def analytics_ingest_enqueue_guard(self) -> dict[str, Any]:
        """Guard ingest queueing using checkpoint timestamp; no extra schema."""
        cooldown_seconds = int(getattr(settings, 'analytics_ingest_enqueue_cooldown_seconds', 120) or 120)
        cp = self.db.query(AnalyticsIngestCheckpoint).filter(AnalyticsIngestCheckpoint.checkpoint_key == 'openedx_tracking_log').first()
        now = datetime.utcnow()
        recent = bool(cp and cp.last_run_at and cp.last_run_at >= now - timedelta(seconds=cooldown_seconds))
        enabled = bool(getattr(settings, 'analytics_ingest_enabled', True))
        return {
            'allowed': bool(enabled and not recent),
            'enabled': enabled,
            'cooldown_seconds': cooldown_seconds,
            'last_run_at': cp.last_run_at.isoformat() if cp and cp.last_run_at else None,
            'reasons': ([] if enabled else ['INGEST_DISABLED']) + (['RECENT_INGEST_RUN'] if recent else []),
            'message': 'Có thể ingest.' if enabled and not recent else 'Ingest đang tắt hoặc vừa chạy gần đây, hãy kiểm tra /jobs hoặc trạng thái ingest.',
            'safe_policy': 'signals_only_not_violation',
        }

    def production_readiness_report(self, *, allowed_class_ids: set[str] | None = None) -> dict[str, Any]:
        """Final production gate for analytics.

        Readiness is computed from checkpoint/snapshot/job metadata only. It does
        not open or scan tracking.log, so it is safe for health checks.
        """
        data_quality = self.analytics_data_quality_report(allowed_class_ids=allowed_class_ids)
        rollout = self.rollout_control_report(allowed_class_ids=allowed_class_ids, limit=200)
        monitoring = self.analytics_monitoring_report(allowed_class_ids=allowed_class_ids)
        ingest = self.ingest_status()
        event_count = self.db.query(AnalyticsTrackingEvent.id).count()
        snapshot_q = self.db.query(AnalyticsLearningBehaviorSnapshot.id)
        if allowed_class_ids is not None:
            snapshot_q = snapshot_q.filter(AnalyticsLearningBehaviorSnapshot.class_id.in_(sorted(allowed_class_ids))) if allowed_class_ids else snapshot_q.filter(False)
        snapshot_count = snapshot_q.count()
        active_jobs = self.db.query(AcademicClassSyncJob.id).filter(
            AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        ).count()
        issues: list[dict[str, Any]] = []
        if not ingest.get('file_exists'):
            issues.append({'code': 'TRACKING_LOG_NOT_MOUNTED', 'severity': 'BLOCKER', 'message': 'Chưa mount tracking.log read-only vào AI Server.', 'action': 'Kiểm tra OPENEDX_TRACKING_LOG_HOST_DIR và docker-compose.prod.yml.'})
        if not ingest.get('enabled'):
            issues.append({'code': 'INGEST_DISABLED', 'severity': 'BLOCKER', 'message': 'ANALYTICS_INGEST_ENABLED đang tắt.', 'action': 'Bật ingest hoặc chạy manual ingest trước khi dùng production.'})
        if not bool(getattr(settings, 'analytics_ingest_scheduler_enabled', False)):
            issues.append({'code': 'SCHEDULER_DISABLED', 'severity': 'WARNING', 'message': 'Scheduler ingest tự động đang tắt.', 'action': 'Bật ANALYTICS_INGEST_SCHEDULER_ENABLED=true khi chạy production.'})
        if event_count < int(getattr(settings, 'analytics_production_min_events', 1) or 1):
            issues.append({'code': 'NO_TRACKING_EVENTS_INGESTED', 'severity': 'BLOCKER', 'message': 'Chưa có tracking event được ingest.', 'action': 'Chạy ingest/backfill trước khi dùng dashboard.'})
        if snapshot_count < int(getattr(settings, 'analytics_production_min_snapshots', 1) or 1):
            issues.append({'code': 'NO_BEHAVIOR_SNAPSHOTS', 'severity': 'BLOCKER', 'message': 'Chưa có snapshot nhận định học online.', 'action': 'Chạy backfill/tính lại học online cho lớp.'})
        if active_jobs > int(getattr(settings, 'analytics_backfill_max_active_jobs', 20) or 20):
            issues.append({'code': 'TOO_MANY_ACTIVE_ANALYTICS_JOBS', 'severity': 'WARNING', 'message': 'Đang có nhiều job học online chạy cùng lúc.', 'action': 'Chờ job hoàn tất trước khi backfill thêm.'})
        if not rollout.get('enabled'):
            issues.append({'code': 'ANALYTICS_ROLLOUT_DISABLED', 'severity': 'BLOCKER', 'message': 'Rollout học online đang tắt.', 'action': 'Bật ANALYTICS_ROLLOUT_ENABLED=true và chọn mode pilot/production.'})
        if rollout.get('enabled') and int((rollout.get('counters') or {}).get('in_rollout') or 0) <= 0:
            issues.append({'code': 'NO_CLASS_IN_ROLLOUT_SCOPE', 'severity': 'WARNING', 'message': 'Chưa có lớp nào trong phạm vi rollout.', 'action': 'Kiểm tra allowlist campus/class/course hoặc mở rộng rollout mode.'})
        if monitoring.get('monitoring_status') == 'BLOCKED':
            issues.append({'code': 'ANALYTICS_MONITORING_BLOCKED', 'severity': 'BLOCKER', 'message': 'Monitoring phát hiện blocker cho học online.', 'action': 'Mở /analytics/learning để xem stuck job, mount log hoặc snapshot stale.'})
        issues.extend(data_quality.get('issues') or [])
        issues.extend([{'code': i.get('code'), 'severity': str(i.get('severity', 'WARNING')).upper(), 'message': i.get('message'), 'action': i.get('action')} for i in (rollout.get('issues') or [])])
        issues.extend([{'code': i.get('code'), 'severity': str(i.get('severity', 'warning')).upper(), 'message': i.get('message'), 'action': i.get('action')} for i in (monitoring.get('issues') or [])])
        blocker_count = len([i for i in issues if str(i.get('severity')).upper() == 'BLOCKER'])
        warning_count = len([i for i in issues if str(i.get('severity')).upper() == 'WARNING'])
        ready = blocker_count == 0
        return {
            'version': '25.9.16.7.2.7',
            'ready_for_production': ready,
            'readiness': 'PRODUCTION_READY' if ready else 'NOT_READY',
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'issue_count': len(issues),
            'issues': issues,
            'checks': {
                'tracking_log_mounted': bool(ingest.get('file_exists')),
                'ingest_enabled': bool(ingest.get('enabled')),
                'scheduler_enabled': bool(getattr(settings, 'analytics_ingest_scheduler_enabled', False)),
                'tracking_event_count': int(event_count or 0),
                'behavior_snapshot_count': int(snapshot_count or 0),
                'active_recalculate_jobs': int(active_jobs or 0),
                'data_quality_readiness': data_quality.get('readiness'),
                'rollout_status': rollout.get('rollout_status'),
                'rollout_mode': rollout.get('mode'),
                'rollout_in_scope_classes': (rollout.get('counters') or {}).get('in_rollout', 0),
                'monitoring_status': monitoring.get('monitoring_status'),
                'stuck_analytics_job_count': monitoring.get('stuck_analytics_job_count'),
                'stale_snapshot_count': monitoring.get('stale_snapshot_count'),
            },
            'rollout_control': rollout,
            'monitoring': monitoring,
            'next_actions': [i.get('action') for i in issues if i.get('action')],
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.',
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
            'version': '25.9.16.7.2.7',
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


    def ops_status(self) -> dict[str, Any]:
        """Production ops snapshot for scheduler/smoke tests.

        This reads checkpoint and snapshot tables only. It never scans the
        tracking log and is safe to call from health/smoke checks.
        """
        ingest = self.ingest_status()
        active_recalc = self.db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        ).count()
        latest_behavior = self.db.query(AnalyticsLearningBehaviorSnapshot).order_by(
            AnalyticsLearningBehaviorSnapshot.calculated_at.desc()
        ).first()
        event_count = self.db.query(AnalyticsTrackingEvent.id).count()
        snapshot_count = self.db.query(AnalyticsLearningBehaviorSnapshot.id).count()
        guard = self.analytics_data_quality_report()
        rollout = self.rollout_control_report(limit=200)
        monitoring = self.analytics_monitoring_report()
        production = self.production_readiness_report()
        return {
            'version': '25.9.16.7.2.7',
            'scheduler_enabled': bool(getattr(settings, 'analytics_ingest_scheduler_enabled', False)),
            'ingest': ingest,
            'active_recalculate_jobs': int(active_recalc or 0),
            'tracking_event_count': int(event_count or 0),
            'behavior_snapshot_count': int(snapshot_count or 0),
            'latest_behavior_calculated_at': latest_behavior.calculated_at.isoformat() if latest_behavior and latest_behavior.calculated_at else None,
            'data_quality_readiness': guard.get('readiness'),
            'data_quality_issue_count': len(guard.get('issues') or []),
            'production_readiness': production.get('readiness'),
            'ready_for_production': bool(production.get('ready_for_production')),
            'production_blocker_count': int(production.get('blocker_count') or 0),
            'production_warning_count': int(production.get('warning_count') or 0),
            'rollout_status': rollout.get('rollout_status'),
            'rollout_mode': rollout.get('mode'),
            'rollout_in_scope_classes': (rollout.get('counters') or {}).get('in_rollout', 0),
            'monitoring_status': monitoring.get('monitoring_status'),
            'stuck_analytics_job_count': monitoring.get('stuck_analytics_job_count'),
            'stale_snapshot_count': monitoring.get('stale_snapshot_count'),
            'safe_policy': 'signals_only_not_violation',
        }

    def _apply_behavior_common_filters(
        self,
        q,
        *,
        campus: str | None = None,
        branch: str | None = None,
        course_id: str | None = None,
        class_id: str | None = None,
        classification: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        allowed_class_ids: set[str] | None = None,
    ):
        start = self._parse_datetime_filter(date_from)
        end = self._parse_datetime_filter(date_to)
        if end:
            end = end + timedelta(days=1) if end.hour == 0 and end.minute == 0 and end.second == 0 else end
        if allowed_class_ids is not None:
            if not allowed_class_ids:
                q = q.filter(False)
            else:
                q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id.in_(sorted(allowed_class_ids)))
        if class_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if course_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)
        if classification and classification != 'all':
            normalized_classification = str(classification).strip().upper()
            if normalized_classification in {'POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING'}:
                q = q.filter(AnalyticsLearningBehaviorSnapshot.classification.in_(['POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING']))
            else:
                q = q.filter(AnalyticsLearningBehaviorSnapshot.classification == normalized_classification)
        if start:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.calculated_at >= start)
        if end:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.calculated_at < end)
        if campus or branch:
            q = q.join(AcademicClass, AcademicClass.id == AnalyticsLearningBehaviorSnapshot.class_id)
            if campus:
                q = q.filter(AcademicClass.campus == campus)
            if branch:
                q = q.filter(AcademicClass.branch == branch)
        return q

    def _course_for_class(self, class_id: str | None, preferred_course_id: str | None = None) -> str | None:
        """Resolve the Open edX course for a class using existing mapping tables.

        Class detail may inherit the course from subject/term/campus scope rather
        than having an explicit AcademicClassCourseMapping row. Older analytics
        code only checked the class override table, so dashboard/backfill showed
        "Chưa map course" even when the class page already displayed Course CMS.
        Keep this read-only and reuse existing schema; do not create rollout or
        analytics mapping tables.
        """
        if preferred_course_id:
            return preferred_course_id
        if not class_id:
            return None
        mapping = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id == class_id,
            AcademicClassCourseMapping.active.is_(True),
        ).first()
        if mapping and mapping.openedx_course_id:
            return mapping.openedx_course_id

        cls = self.db.query(AcademicClass).filter(AcademicClass.id == class_id).first()
        if not cls:
            return None

        q = self.db.query(AcademicCourseMapping).filter(
            AcademicCourseMapping.term_id == cls.term_id,
            AcademicCourseMapping.subject_id == cls.subject_id,
            AcademicCourseMapping.active.is_(True),
        )
        # Prefer exact block/campus/branch scope, then gracefully fall back to the
        # broader subject-term mapping used by existing student/class screens.
        candidates = q.all()
        if not candidates:
            return None

        def score(item: AcademicCourseMapping) -> tuple[int, datetime]:
            value = 0
            if (item.block_id or None) == (cls.block_id or None):
                value += 8
            elif item.block_id is None:
                value += 2
            if (item.campus or '').strip().lower() == (cls.campus or '').strip().lower():
                value += 4
            elif not item.campus:
                value += 1
            if (item.branch or '').strip().lower() == (cls.branch or '').strip().lower():
                value += 4
            elif not item.branch:
                value += 1
            return (value, item.updated_at or item.created_at or datetime.min)

        best = sorted(candidates, key=score, reverse=True)[0]
        return best.openedx_course_id if best and best.openedx_course_id else None

    def _class_student_usernames(self, class_id: str | None) -> set[str]:
        if not class_id:
            return set()
        rows = self.db.query(AcademicStudent.username).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).filter(AcademicClassStudent.class_id == class_id).all()
        return {str(row[0]) for row in rows if row and row[0]}

    def _class_student_roster(self, class_id: str | None) -> list[dict[str, Any]]:
        """Return the AP roster for a class as the canonical analytics fallback.

        Learning-behavior screens must never show "0 sinh viên" just because the
        behavior snapshot job has not materialized rows yet. The roster is the
        ground truth for who belongs to the class; missing behavior snapshots are
        represented as INSUFFICIENT_DATA rows so teachers can see that the class
        exists and then decide whether to run/retry recalculation.
        """
        if not class_id:
            return []
        rows = self.db.query(AcademicStudent).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).filter(
            AcademicClassStudent.class_id == class_id,
            AcademicStudent.active.is_(True),
        ).order_by(AcademicStudent.username.asc()).all()
        return [
            {
                'student_id': str(item.id),
                'username': item.username,
                'student_code': item.student_code,
                'full_name': item.full_name,
                'email': item.email,
            }
            for item in rows
            if item and item.username
        ]

    @staticmethod
    def _normal_username(value: str | None) -> str:
        return str(value or '').strip().lower()

    def class_video_summary(self, *, class_id: str | None, course_id: str | None = None) -> dict[str, Any]:
        resolved_course = self._course_for_class(class_id, course_id)
        if not resolved_course:
            return {
                'class_id': class_id,
                'course_id': course_id,
                'total_students': 0,
                'students_with_video_activity': 0,
                'students_without_video_activity': 0,
                'avg_completion_percent': None,
                'avg_watch_seconds': None,
                'completed_video_count': 0,
                'low_activity_student_count': 0,
                'possible_idle_count': 0,
                'possible_suspicious_count': 0,
                'likely_real_learning_count': 0,
                'insufficient_data_count': 0,
                'disclaimer': 'Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.',
            }
        class_users = self._class_student_usernames(class_id)
        q = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.course_id == resolved_course)
        if class_users:
            q = q.filter(AnalyticsStudentVideoProgress.username.in_(class_users))
        rows = q.all()
        students_with = {r.username for r in rows if r.username}
        total_students = len(class_users) or len(students_with)
        behavior = self.behavior_summary(class_id=class_id, course_id=resolved_course)
        avg_completion = round(sum(float(r.completion_percent or 0) for r in rows) / len(rows), 2) if rows else None
        avg_watch = round(sum(float(r.estimated_watch_seconds or 0) for r in rows) / len(rows), 2) if rows else None
        low_activity = len({r.username for r in rows if (r.completion_percent or 0) >= 90 and (r.estimated_watch_percent or 0) < 25})
        return {
            'class_id': class_id,
            'course_id': resolved_course,
            'total_students': total_students,
            'students_with_video_activity': len(students_with),
            'students_without_video_activity': max(0, total_students - len(students_with)),
            'avg_completion_percent': avg_completion,
            'avg_watch_seconds': avg_watch,
            'completed_video_count': len([r for r in rows if r.is_completed]),
            'low_activity_student_count': low_activity,
            'possible_idle_count': behavior.get('possible_idle_count', 0),
            'possible_suspicious_count': behavior.get('possible_suspicious_count', 0),
            'likely_real_learning_count': behavior.get('likely_real_learning_count', 0),
            'insufficient_data_count': behavior.get('insufficient_data_count', 0),
            'disclaimer': behavior.get('disclaimer'),
        }

    def class_sessions_progress(self, *, class_id: str | None, course_id: str | None = None) -> dict[str, Any]:
        resolved_course = self._course_for_class(class_id, course_id)
        if not resolved_course:
            return {'class_id': class_id, 'course_id': course_id, 'items': [], 'total': 0}
        class_users = self._class_student_usernames(class_id)
        q = self.db.query(AnalyticsStudentSessionProgress).filter(AnalyticsStudentSessionProgress.course_id == resolved_course)
        if class_users:
            q = q.filter(AnalyticsStudentSessionProgress.username.in_(class_users))
        rows = q.all()
        by_session: dict[int, list[AnalyticsStudentSessionProgress]] = defaultdict(list)
        for row in rows:
            by_session[int(row.session_index or 0)].append(row)
        items: list[dict[str, Any]] = []
        total_students = len(class_users) or len({r.username for r in rows if r.username})
        for idx in sorted(k for k in by_session if k > 0):
            group = by_session[idx]
            first = group[0]
            items.append({
                'session_index': idx,
                'session_title': first.session_title,
                'week_index': first.week_index,
                'deadline_at': first.deadline_at.isoformat() if first.deadline_at else None,
                'deadline_source': first.deadline_source,
                'total_students': total_students,
                'completed_before_deadline_count': len([r for r in group if r.completed_before_deadline is True]),
                'completed_late_count': len([r for r in group if r.completed_late is True]),
                'not_started_count': max(0, total_students - len([r for r in group if r.started_at])),
                'possible_idle_count': len([r for r in group if r.session_learning_status == 'POSSIBLE_IDLE']),
                'possible_suspicious_count': len([r for r in group if r.session_learning_status == 'POSSIBLE_SUSPICIOUS']),
                'avg_video_completion_percent': round(sum(float(r.avg_video_completion_percent or 0) for r in group) / len(group), 2) if group else None,
                'avg_watch_seconds': round(sum(float(r.estimated_watch_seconds or 0) for r in group) / len(group), 2) if group else None,
            })
        return {'class_id': class_id, 'course_id': resolved_course, 'total': len(items), 'items': items}

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

    @staticmethod
    def _timeline_weeks_from_sessions(rows: list[AnalyticsStudentSessionProgress]) -> list[dict[str, Any]]:
        by_week: dict[int, list[AnalyticsStudentSessionProgress]] = defaultdict(list)
        for row in rows:
            by_week[int(row.week_index or 0)].append(row)
        result: list[dict[str, Any]] = []
        for week in sorted(k for k in by_week if k > 0):
            result.append({'week_index': week, 'sessions': [r.session_index for r in sorted(by_week[week], key=lambda item: item.session_index)]})
        return result


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

    @staticmethod
    def _empty_class_behavior_overview_summary() -> dict[str, Any]:
        return {
            'total_classes': 0,
            'total_students': 0,
            'roster_count': 0,
            'snapshot_count': 0,
            'missing_snapshot_count': 0,
            'likely_real_learning_count': 0,
            'possible_idle_count': 0,
            'possible_suspicious_count': 0,
            'insufficient_data_count': 0,
            'normal_count': 0,
            'not_calculated_class_count': 0,
            'last_activity_at': None,
            'calculated_at': None,
        }

    @staticmethod
    def _class_behavior_focus_count(behavior: dict[str, Any], classification: str) -> int:
        if classification == 'LIKELY_REAL_LEARNING':
            return int(behavior.get('likely_real_learning_count') or 0)
        if classification == 'POSSIBLE_IDLE':
            return int(behavior.get('possible_idle_count') or 0)
        if classification == 'POSSIBLE_ANOMALY':
            return int(behavior.get('possible_suspicious_count') or 0)
        if classification == 'INSUFFICIENT_DATA':
            return int(behavior.get('insufficient_data_count') or 0)
        if classification == 'NORMAL':
            return int(behavior.get('normal_count') or 0)
        return int(behavior.get('total_students') or 0)

    @staticmethod
    def _dominant_classification(behavior: dict[str, Any]) -> str:
        candidates = [
            ('POSSIBLE_ANOMALY', int(behavior.get('possible_suspicious_count') or 0)),
            ('POSSIBLE_IDLE', int(behavior.get('possible_idle_count') or 0)),
            ('INSUFFICIENT_DATA', int(behavior.get('insufficient_data_count') or 0)),
            ('LIKELY_REAL_LEARNING', int(behavior.get('likely_real_learning_count') or 0)),
            ('NORMAL', int(behavior.get('normal_count') or 0)),
        ]
        label, count = max(candidates, key=lambda item: item[1])
        return label if count > 0 else 'INSUFFICIENT_DATA'


    @staticmethod
    def _iso_or_none(value: Any) -> str | None:
        return value.isoformat() if value else None

    def _class_course_mapping_diagnostics(self, *, class_id: str, preferred_course_id: str | None = None) -> dict[str, Any]:
        """Inspect class -> Open edX course resolution without writing data.

        Production incidents around /analytics/learning usually come from a
        missing or ambiguous course mapping, not from the classifier itself. This
        diagnostic keeps the resolver transparent and conservative: exact class
        override wins, inherited subject/term mappings are listed, and ambiguous
        candidates are not auto-selected.
        """
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            return {
                'status': 'missing_class',
                'resolved_course_id': preferred_course_id,
                'mapping_source': 'request' if preferred_course_id else None,
                'candidate_count': 0,
                'candidates': [],
                'message': 'Không tìm thấy lớp trong AcademicClass.',
            }

        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_candidate(course_id: str | None, source: str, score: int, mapping: Any = None, note: str = '') -> None:
            clean = str(course_id or '').strip()
            if not clean:
                return
            key = (clean, source)
            if key in seen:
                return
            seen.add(key)
            candidates.append({
                'course_id': clean,
                'source': source,
                'score': int(score),
                'mapping_id': str(getattr(mapping, 'id', '') or '') or None,
                'validation_status': getattr(mapping, 'validation_status', None),
                'updated_at': self._iso_or_none(getattr(mapping, 'updated_at', None)),
                'note': note,
            })

        if preferred_course_id:
            add_candidate(preferred_course_id, 'request', 100, None, 'Course ID được truyền từ UI/API.')

        direct_rows = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id == class_id,
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).all()
        for row in direct_rows:
            add_candidate(row.openedx_course_id, 'class_override', 90, row, 'Mapping trực tiếp theo lớp.')

        mappings = self.db.query(AcademicCourseMapping).filter(
            AcademicCourseMapping.term_id == cls.term_id,
            AcademicCourseMapping.subject_id == cls.subject_id,
            AcademicCourseMapping.active.is_(True),
        ).all()
        for row in mappings:
            score = 30
            if (row.block_id or None) == (cls.block_id or None):
                score += 20
            elif row.block_id is None:
                score += 5
            if (row.campus or '').strip().lower() == (cls.campus or '').strip().lower():
                score += 15
            elif not row.campus:
                score += 3
            if (row.branch or '').strip().lower() == (cls.branch or '').strip().lower():
                score += 15
            elif not row.branch:
                score += 3
            add_candidate(row.openedx_course_id, 'subject_term_mapping', score, row, 'Mapping kế thừa theo môn/kỳ/cơ sở/hệ.')

        candidates.sort(key=lambda item: (int(item.get('score') or 0), str(item.get('updated_at') or '')), reverse=True)
        course_ids = []
        for item in candidates:
            cid = str(item.get('course_id') or '')
            if cid and cid not in course_ids:
                course_ids.append(cid)

        if not course_ids:
            status = 'missing'
            resolved = None
            source = None
            message = 'Lớp chưa ghép Course CMS/Open edX.'
        elif len(course_ids) == 1:
            status = 'resolved'
            resolved = course_ids[0]
            source = next((item.get('source') for item in candidates if item.get('course_id') == resolved), None)
            message = 'Đã xác định được Course CMS/Open edX cho lớp.'
        else:
            top_score = int(candidates[0].get('score') or 0)
            top_courses = [str(item.get('course_id')) for item in candidates if int(item.get('score') or 0) == top_score]
            if len(set(top_courses)) == 1:
                status = 'resolved'
                resolved = top_courses[0]
                source = next((item.get('source') for item in candidates if item.get('course_id') == resolved), None)
                message = 'Đã chọn course có độ khớp cao nhất.'
            else:
                status = 'ambiguous'
                resolved = None
                source = None
                message = 'Có nhiều Course CMS có thể khớp lớp này; hệ thống không tự chọn bừa.'

        return {
            'status': status,
            'resolved_course_id': resolved,
            'mapping_source': source,
            'candidate_count': len(course_ids),
            'mapped_course_ids': course_ids,
            'candidates': candidates[:10],
            'message': message,
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
