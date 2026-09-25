from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.json_safe import json_safe_value
from app.core.privacy import mask_email
from app.models.academic import AcademicBlock, AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob, AcademicCourseMapping, AcademicQuizDeadlineOverride, AcademicStudent, AcademicStudentLearningSnapshot, AcademicTerm, OpenEdXUserMapping
from app.models.course import CourseSyncState
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
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.learning_analytics.tracking_event_parser import TrackingParseError, parse_tracking_log_line
from app.services.learning_analytics.quiz_attempt_analyzer import EventLike, build_quiz_attempt_features
from app.services.learning_analytics.tracking_log_reader import TrackingLogReader
from app.services.learning_analytics.loki_tracking_reader import LokiTrackingLogReader
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress
from app.services.openedx_client import OpenEdxClient
from app.services.learning_analytics.presentation import (
    class_behavior_focus_count as _presentation_class_behavior_focus_count,
    csv_setting_set as _presentation_csv_setting_set,
    dominant_classification as _presentation_dominant_classification,
    empty_class_behavior_overview_summary as _presentation_empty_class_behavior_overview_summary,
    iso_or_none as _presentation_iso_or_none,
    parse_datetime_filter as _presentation_parse_datetime_filter,
    recommended_action_label as _presentation_recommended_action_label,
    safe_label as _presentation_safe_label,
    sla_status as _presentation_sla_status,
    timeline_weeks_from_sessions as _presentation_timeline_weeks_from_sessions,
)
from app.services.learning_analytics.operations import LearningAnalyticsOperationsWorkflowService
from app.services.learning_analytics.results import LearningAnalyticsResultsWorkflowService


VIDEO_EVENT_TYPES = {'play_video', 'pause_video', 'stop_video', 'seek_video', 'edx.video.played', 'edx.video.paused', 'edx.video.stopped', 'edx.video.position.changed'}
PROBLEM_EVENT_TYPES = {'problem_check', 'problem_graded', 'problem_save', 'edx.grades.problem.submitted', 'edx.completion.block_completion.changed'}
QUIZ_SESSION_EVENT_TYPES = {'/api/unit-reset/v1/quiz-session/start', '/api/unit-reset/v1/quiz-session/status', '/api/unit-reset/v1/quiz-session/reset'}
ITEMBANK_EVENT_TYPES = {'edx.itembankblock.content.assigned'}
ANSWER_REVEAL_EVENT_TYPES = {'problem_show', 'showanswer'}
QUIZ_ANALYTICS_EVENT_TYPES = PROBLEM_EVENT_TYPES | QUIZ_SESSION_EVENT_TYPES | ITEMBANK_EVENT_TYPES | ANSWER_REVEAL_EVENT_TYPES
ANALYTICS_INGEST_LOCK_ID = 2591672601


class LearningAnalyticsCoreService:
    _safe_label = staticmethod(_presentation_safe_label)
    _recommended_action_label = staticmethod(_presentation_recommended_action_label)
    _parse_datetime_filter = staticmethod(_presentation_parse_datetime_filter)
    _csv_setting_set = staticmethod(_presentation_csv_setting_set)
    _sla_status = staticmethod(_presentation_sla_status)
    _timeline_weeks_from_sessions = staticmethod(_presentation_timeline_weeks_from_sessions)
    _empty_class_behavior_overview_summary = staticmethod(_presentation_empty_class_behavior_overview_summary)
    _class_behavior_focus_count = staticmethod(_presentation_class_behavior_focus_count)
    _dominant_classification = staticmethod(_presentation_dominant_classification)
    _iso_or_none = staticmethod(_presentation_iso_or_none)
    def __init__(self, db: Session):
        self.db = db

    def _analytics_operations_workflow(self) -> LearningAnalyticsOperationsWorkflowService:
        return LearningAnalyticsOperationsWorkflowService(self)

    def _analytics_results_workflow(self) -> LearningAnalyticsResultsWorkflowService:
        return LearningAnalyticsResultsWorkflowService(self)

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
        source = str(getattr(settings, 'analytics_ingest_source', 'loki') or 'loki').strip().lower()
        if source == 'loki':
            base_url = str(getattr(settings, 'analytics_loki_base_url', '') or '').strip().rstrip('/')
            cp = self.db.query(AnalyticsIngestCheckpoint).filter(
                AnalyticsIngestCheckpoint.checkpoint_key == 'openedx_tracking_loki'
            ).first()
            return {
                'enabled': True,
                'source': 'loki',
                'source_url': base_url,
                # Compatibility for existing SLA/UI code that historically
                # interpreted file_exists as "ingest source is available".
                'file_path': None,
                'file_exists': True,
                'checkpoint_key': 'openedx_tracking_loki',
                'last_offset': int(cp.last_offset or 0) if cp else 0,
                'cursor_ns': str(int(cp.last_offset or 0)) if cp else '0',
                'last_run_at': cp.last_run_at.isoformat() if cp and cp.last_run_at else None,
                'last_status': cp.last_status if cp else 'never_run',
                'last_error': cp.last_error if cp else None,
                'total_lines_read': int(cp.total_lines_read or 0) if cp else 0,
                'total_events_inserted': int(cp.total_events_inserted or 0) if cp else 0,
                'total_duplicate_events': int(cp.total_duplicate_events or 0) if cp else 0,
                'total_parse_errors': int(cp.total_parse_errors or 0) if cp else 0,
                'stats': cp.stats_json if cp else {},
            }

        file_path = getattr(settings, 'openedx_tracking_log_path', '/openedx-data/lms/logs/tracking.log')
        cp = self.db.query(AnalyticsIngestCheckpoint).filter(AnalyticsIngestCheckpoint.checkpoint_key == 'openedx_tracking_log').first()
        exists = Path(file_path).exists()
        return {
            'enabled': True,
            'source': 'file',
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

    @staticmethod
    def _mapping_scope_value_matches(mapping_value: Any, class_value: Any) -> bool:
        """Return whether one optional subject-mapping scope matches a class.

        A blank mapping scope is a wildcard. A non-blank mapping scope must
        match the class exactly (case-insensitive for string values).
        """
        left = str(mapping_value or '').strip().lower()
        if not left:
            return True
        return left == str(class_value or '').strip().lower()

    @classmethod
    def _subject_mapping_matches_class(cls, mapping: AcademicCourseMapping, klass: AcademicClass) -> bool:
        return (
            str(mapping.term_id or '') == str(klass.term_id or '')
            and str(mapping.subject_id or '') == str(klass.subject_id or '')
            and cls._mapping_scope_value_matches(mapping.block_id, klass.block_id)
            and cls._mapping_scope_value_matches(mapping.campus, klass.campus)
            and cls._mapping_scope_value_matches(mapping.branch, klass.branch)
        )

    @classmethod
    def _subject_mapping_score_for_class(cls, mapping: AcademicCourseMapping, klass: AcademicClass) -> int | None:
        """Score only mappings that are actually eligible for the class.

        Exact block/campus/branch scopes outrank wildcards. A mismatched
        non-blank scope is not a lower-confidence candidate; it is ineligible.
        """
        if not cls._subject_mapping_matches_class(mapping, klass):
            return None
        score = 30
        score += 20 if str(mapping.block_id or '').strip() else 5
        score += 15 if str(mapping.campus or '').strip() else 3
        score += 15 if str(mapping.branch or '').strip() else 3
        return score

    def _class_scope_filter(self, q: Any, column: Any, value: Any) -> Any:
        """Apply an optional AcademicCourseMapping scope to AcademicClass."""
        if value is None or str(value).strip() == '':
            return q
        return q.filter(column == value)

    def _resolve_recalculate_class_ids_for_courses(self, *, course_ids: set[str]) -> dict[str, set[str]]:
        """Resolve only the effective Open edX course for each active AP class.

        Resolution precedence matches the diagnostics/UI contract:
        class override > most-specific eligible subject/term mapping > wildcard.
        Ambiguous equal-score mappings are deliberately not auto-selected.
        """
        clean_course_ids = {
            str(course_id or '').strip()
            for course_id in course_ids
            if str(course_id or '').strip()
        }
        if not clean_course_ids:
            return {}

        resolved: dict[str, set[str]] = defaultdict(set)

        # Class overrides are authoritative and win over inherited mappings.
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

        relevant_mappings = (
            self.db.query(AcademicCourseMapping)
            .filter(
                AcademicCourseMapping.active.is_(True),
                AcademicCourseMapping.openedx_course_id.in_(list(clean_course_ids)),
            )
            .all()
        )
        if not relevant_mappings:
            return resolved

        relevant_pairs = {
            (str(mapping.term_id or ''), str(mapping.subject_id or ''))
            for mapping in relevant_mappings
            if mapping.term_id and mapping.subject_id
        }
        term_ids = {pair[0] for pair in relevant_pairs}
        subject_ids = {pair[1] for pair in relevant_pairs}

        classes = (
            self.db.query(AcademicClass)
            .filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id.in_(list(term_ids)),
                AcademicClass.subject_id.in_(list(subject_ids)),
            )
            .all()
        )
        classes = [
            klass for klass in classes
            if (str(klass.term_id or ''), str(klass.subject_id or '')) in relevant_pairs
        ]
        if not classes:
            return resolved

        class_ids = [str(klass.id) for klass in classes if klass.id]
        direct_overrides = (
            self.db.query(AcademicClassCourseMapping)
            .filter(
                AcademicClassCourseMapping.active.is_(True),
                AcademicClassCourseMapping.class_id.in_(class_ids),
            )
            .all()
        )
        override_by_class = {
            str(row.class_id): str(row.openedx_course_id or '').strip()
            for row in direct_overrides
            if row.class_id and str(row.openedx_course_id or '').strip()
        }

        # Load every inherited mapping for the involved term/subject pairs so a
        # broad mapping cannot incorrectly beat a more specific mapping that
        # points to a different course.
        all_pair_mappings = (
            self.db.query(AcademicCourseMapping)
            .filter(
                AcademicCourseMapping.active.is_(True),
                AcademicCourseMapping.term_id.in_(list(term_ids)),
                AcademicCourseMapping.subject_id.in_(list(subject_ids)),
            )
            .all()
        )
        mappings_by_pair: dict[tuple[str, str], list[AcademicCourseMapping]] = defaultdict(list)
        for mapping in all_pair_mappings:
            pair = (str(mapping.term_id or ''), str(mapping.subject_id or ''))
            if pair in relevant_pairs:
                mappings_by_pair[pair].append(mapping)

        for klass in classes:
            class_id = str(klass.id or '')
            if not class_id:
                continue

            override_course_id = override_by_class.get(class_id)
            if override_course_id:
                if override_course_id in clean_course_ids:
                    resolved[override_course_id].add(class_id)
                continue

            pair = (str(klass.term_id or ''), str(klass.subject_id or ''))
            scored: list[tuple[int, str]] = []
            for mapping in mappings_by_pair.get(pair, []):
                course_id = str(mapping.openedx_course_id or '').strip()
                if not course_id:
                    continue
                score = self._subject_mapping_score_for_class(mapping, klass)
                if score is not None:
                    scored.append((score, course_id))

            if not scored:
                continue

            top_score = max(score for score, _course_id in scored)
            top_courses = {
                course_id for score, course_id in scored
                if score == top_score
            }
            if len(top_courses) != 1:
                # Equal-confidence mappings are ambiguous. Leave the class out
                # of automatic recalculation rather than choosing arbitrarily.
                continue

            effective_course_id = next(iter(top_courses))
            if effective_course_id in clean_course_ids:
                resolved[effective_course_id].add(class_id)

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
        delivery_service = AcademicSubjectDeliveryService(self.db)

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
                try:
                    class_row = self.db.get(AcademicClass, class_id)
                    delivery = delivery_service.delivery_for_class(class_row) if class_row else None
                    if delivery and delivery.learning_platform == 'udemy':
                        skipped['UDEMY_PLATFORM'] += 1
                        continue
                except Exception:
                    skipped['PLATFORM_LOOKUP_ERROR'] += 1
                    continue
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
        """Ingest Open edX tracking events from the configured production source."""
        source = str(getattr(settings, 'analytics_ingest_source', 'loki') or 'loki').strip().lower()
        # Explicit file_path keeps the manual/debug compatibility path intact.
        if file_path or source == 'file':
            return self._run_file_ingest(file_path=file_path, max_lines=max_lines)
        if source != 'loki':
            raise ValueError(f'Unsupported ANALYTICS_INGEST_SOURCE: {source}')
        return self._run_loki_ingest(max_lines=max_lines)

    def _run_loki_ingest(self, *, max_lines: int | None = None) -> dict[str, Any]:
        if not self._try_acquire_ingest_lock():
            return {
                'enabled': True,
                'source': 'loki',
                'status': 'skipped_locked',
                'message': 'Một lượt ingest tracking log khác đang chạy.',
                'safe_policy': 'signals_only_not_violation',
            }

        base_url = str(getattr(settings, 'analytics_loki_base_url', '') or '').strip().rstrip('/')
        query = str(getattr(settings, 'analytics_loki_query', '') or '').strip()
        checkpoint_key = 'openedx_tracking_loki'
        cp: AnalyticsIngestCheckpoint | None = None
        try:
            cp = self._get_checkpoint(checkpoint_key, base_url)
            reader = LokiTrackingLogReader(
                base_url=base_url,
                query=query,
                window_seconds=int(getattr(settings, 'analytics_loki_window_seconds', 600) or 600),
                lag_seconds=int(getattr(settings, 'analytics_loki_lag_seconds', 120) or 120),
                limit=int(getattr(settings, 'analytics_loki_limit', 1000) or 1000),
                timeout_seconds=float(getattr(settings, 'analytics_loki_request_timeout_seconds', 60) or 60),
                page_sleep_seconds=float(getattr(settings, 'analytics_loki_page_sleep_seconds', 0.3) or 0.0),
                max_pages=int(getattr(settings, 'analytics_loki_max_pages_per_run', 100) or 100),
                max_lines=max_lines or int(getattr(settings, 'analytics_max_lines_per_run', 50000) or 50000),
                tenant_id=str(getattr(settings, 'analytics_loki_tenant_id', '') or '').strip() or None,
            )
            cursor_ns = int(cp.last_offset or 0)
            if cursor_ns <= 0:
                configured_start_ns = int(getattr(settings, 'analytics_loki_backfill_start_ns', 0) or 0)
                cursor_ns = configured_start_ns if configured_start_ns > 0 else reader.initial_cursor_ns(
                    backfill_start=str(getattr(settings, 'analytics_loki_backfill_start', '') or '').strip() or None,
                    default_backfill_hours=int(getattr(settings, 'analytics_loki_default_backfill_hours', 24) or 24),
                )

            result = reader.read_from(cursor_ns=cursor_ns)
            stats = Counter()
            stats['lines_read'] = len(result.entries)
            event_type_counts: Counter[str] = Counter()
            impacted_course_usernames: dict[str, set[str]] = defaultdict(set)
            parsed_rows: list[tuple[Any, Any]] = []
            for entry in result.entries:
                try:
                    # Loki remains the complete raw source of truth. PostgreSQL
                    # stores only events required by learning analytics.
                    parsed = parse_tracking_log_line(entry.line, relevant_only=True)
                except TrackingParseError:
                    stats['parse_errors'] += 1
                    continue
                if parsed is None:
                    stats['ignored_events'] += 1
                    continue
                parsed_rows.append((entry, parsed))
                event_type_counts[parsed.event_type] += 1

            existing_hashes: set[str] = set()
            hashes = list(dict.fromkeys(parsed.raw_line_hash for _entry, parsed in parsed_rows))
            for offset in range(0, len(hashes), 1000):
                batch = hashes[offset:offset + 1000]
                existing_hashes.update(
                    str(raw_hash)
                    for (raw_hash,) in self.db.query(AnalyticsTrackingEvent.raw_line_hash)
                    .filter(AnalyticsTrackingEvent.raw_line_hash.in_(batch))
                    .all()
                    if raw_hash
                )

            seen_hashes = set(existing_hashes)
            for entry, parsed in parsed_rows:
                if parsed.raw_line_hash in seen_hashes:
                    stats['duplicate_events'] += 1
                    continue
                seen_hashes.add(parsed.raw_line_hash)
                values = parsed.as_model_kwargs()
                values.update({
                    'event_source': 'openedx_tracking_loki',
                    'loki_ts_ns': int(entry.timestamp_ns),
                    'source_pod': entry.pod,
                    'source_app': entry.app,
                })
                self.db.add(AnalyticsTrackingEvent(**values))
                stats['events_inserted'] += 1
                if parsed.course_id:
                    impacted_course_usernames[str(parsed.course_id or '').strip()].add(str(parsed.username or '').strip())
                if parsed.event_type in VIDEO_EVENT_TYPES:
                    stats['video_events'] += 1
                if parsed.event_type in PROBLEM_EVENT_TYPES:
                    stats['problem_events'] += 1
                if (stats['events_inserted'] % 500) == 0:
                    self.db.flush()

            cp.file_inode = None
            cp.file_size = 0
            cp.last_offset = int(result.end_cursor_ns)
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
                'source': 'loki',
                'event_type_counts': dict(event_type_counts),
                'start_cursor_ns': str(result.start_cursor_ns),
                'end_cursor_ns': str(result.end_cursor_ns),
                'safe_end_ns': str(result.safe_end_ns),
                'pages': result.pages,
                'windows': result.windows,
                'caught_up': result.caught_up,
                'query': result.query,
                'impacted_course_count': len(impacted_course_usernames),
                'impacted_user_count': sum(len(users) for users in impacted_course_usernames.values()),
            }
            self.db.add(cp)
            self.db.commit()

            post_ingest_recalculate = {
                'enabled': True,
                'status': 'not_run',
            }
            if int(stats['events_inserted'] or 0) > 0:
                try:
                    post_ingest_recalculate = self.enqueue_post_ingest_recalculate_jobs(
                        course_usernames=impacted_course_usernames,
                        source='analytics_loki_ingest_task',
                    )
                except Exception as exc:
                    post_ingest_recalculate = {'enabled': True, 'status': 'failed', 'message': str(exc)[:1000]}

            cp.stats_json = {**(cp.stats_json or {}), 'post_ingest_recalculate': post_ingest_recalculate}
            self.db.add(cp)
            self.db.commit()
            return {
                'enabled': True,
                'source': 'loki',
                'status': 'completed',
                'cursor_ns': str(result.end_cursor_ns),
                **cp.stats_json,
            }
        except Exception as exc:
            self.db.rollback()
            try:
                cp = self._get_checkpoint(checkpoint_key, base_url)
                cp.last_run_at = datetime.utcnow()
                cp.last_status = 'failed'
                cp.last_error = str(exc)[:4000]
                cp.stats_json = {
                    **(cp.stats_json or {}),
                    'source': 'loki',
                    'last_failure': str(exc)[:1000],
                }
                self.db.add(cp)
                self.db.commit()
            except Exception:
                self.db.rollback()
            raise
        finally:
            self._release_ingest_lock()

    def _run_file_ingest(self, *, file_path: str | None = None, max_lines: int | None = None) -> dict[str, Any]:
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
                    parsed = parse_tracking_log_line(line, relevant_only=True)
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
            post_ingest_recalculate = {'enabled': True, 'status': 'not_run'}
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

    def cleanup_tracking_events(self) -> dict[str, Any]:
        """Delete only retention-safe raw video/quiz events in bounded batches.

        Loki remains the raw source of truth. PostgreSQL keeps a short staging
        window while durable video/quiz materializations retain historical
        analytics. Cleanup is intentionally conservative:
        - PostgreSQL only;
        - never while analytics recalculate jobs are queued/running;
        - never before at least one video/quiz materialization exists;
        - delete an event only when a matching durable materialized row exists;
        - keep non-video/non-quiz event families untouched.
        """
        if not self._is_postgres():
            return {
                'status': 'skipped_non_postgres',
                'deleted': 0,
            }

        active_jobs = (
            self.db.query(AcademicClassSyncJob.id)
            .filter(
                AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
                AcademicClassSyncJob.status.in_(['queued', 'running']),
            )
            .count()
        )
        if active_jobs:
            return {
                'status': 'skipped_active_recalculate_jobs',
                'active_jobs': int(active_jobs),
                'deleted': 0,
            }

        video_rows = int(self.db.query(AnalyticsStudentVideoProgress.id).count() or 0)
        quiz_rows = int(self.db.query(AnalyticsQuizAttempt.id).count() or 0)
        if video_rows + quiz_rows <= 0:
            return {
                'status': 'skipped_not_materialized',
                'video_rows': video_rows,
                'quiz_rows': quiz_rows,
                'deleted': 0,
                'message': 'Chưa có video/quiz materialized; giữ nguyên raw events để có thể tính lại.',
            }

        retention_days = max(1, int(getattr(settings, 'analytics_raw_event_retention_days', 7) or 7))
        batch_size = min(
            50000,
            max(100, int(getattr(settings, 'analytics_raw_event_cleanup_batch_size', 20000) or 20000)),
        )
        max_batches = min(
            100,
            max(1, int(getattr(settings, 'analytics_raw_event_cleanup_max_batches_per_run', 10) or 10)),
        )
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        def sql_list(values: set[str]) -> str:
            return ','.join("'" + str(value).replace("'", "''") + "'" for value in sorted(values))

        video_types_sql = sql_list(set(VIDEO_EVENT_TYPES))
        quiz_types_sql = sql_list(set(QUIZ_ANALYTICS_EVENT_TYPES))
        deleted = 0
        batches = 0

        # Match raw Open edX identities to the AP username stored in durable
        # materializations. Direct username equality remains as a safe fallback
        # for installations where AP/Open edX usernames are identical.
        delete_sql = text(f"""
            WITH doomed AS (
                SELECT e.id
                FROM analytics_tracking_events e
                WHERE e.created_at < :cutoff
                  AND (
                    (
                      e.event_type IN ({video_types_sql})
                      AND EXISTS (
                        SELECT 1
                        FROM analytics_student_video_progress v
                        LEFT JOIN openedx_user_mappings m
                          ON (
                            (e.username IS NOT NULL AND m.openedx_username = e.username)
                            OR
                            (e.user_id IS NOT NULL AND m.openedx_user_id = e.user_id)
                          )
                        LEFT JOIN academic_students s
                          ON s.id = m.student_id
                        WHERE v.course_id = e.course_id
                          AND v.video_id = e.video_id
                          AND (
                            v.username = e.username
                            OR v.username = s.username
                          )
                      )
                    )
                    OR
                    (
                      e.event_type IN ({quiz_types_sql})
                      AND EXISTS (
                        SELECT 1
                        FROM analytics_quiz_attempts q
                        LEFT JOIN openedx_user_mappings m
                          ON (
                            (e.username IS NOT NULL AND m.openedx_username = e.username)
                            OR
                            (e.user_id IS NOT NULL AND m.openedx_user_id = e.user_id)
                          )
                        LEFT JOIN academic_students s
                          ON s.id = m.student_id
                        WHERE q.course_id = e.course_id
                          AND (
                            q.username = e.username
                            OR q.username = s.username
                          )
                      )
                    )
                  )
                ORDER BY e.created_at ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            DELETE FROM analytics_tracking_events e
            USING doomed d
            WHERE e.id = d.id
            RETURNING e.id
        """)

        for _ in range(max_batches):
            lock_acquired = bool(
                self.db.execute(
                    text('SELECT pg_try_advisory_xact_lock(:lock_id)'),
                    {'lock_id': ANALYTICS_INGEST_LOCK_ID},
                ).scalar()
            )
            if not lock_acquired:
                self.db.rollback()
                return {
                    'status': 'skipped_ingest_locked',
                    'retention_days': retention_days,
                    'cutoff': cutoff.isoformat(),
                    'deleted': deleted,
                    'batches': batches,
                }
            removed = self.db.execute(
                delete_sql,
                {
                    'cutoff': cutoff,
                    'batch_size': batch_size,
                },
            ).scalars().all()
            removed_count = len(removed)
            # Transaction-scoped advisory lock is released by this commit.
            self.db.commit()
            if removed_count <= 0:
                break
            deleted += removed_count
            batches += 1
            if removed_count < batch_size:
                break

        remaining_old = int(
            self.db.query(AnalyticsTrackingEvent.id)
            .filter(AnalyticsTrackingEvent.created_at < cutoff)
            .count()
            or 0
        )
        return {
            'status': 'completed',
            'retention_days': retention_days,
            'cutoff': cutoff.isoformat(),
            'batch_size': batch_size,
            'max_batches': max_batches,
            'batches': batches,
            'deleted': deleted,
            'remaining_old_rows_all_types': remaining_old,
            'video_rows': video_rows,
            'quiz_rows': quiz_rows,
            'policy': 'delete_only_materialized_video_quiz_raw_events',
        }

    def _course_start_at_for_class(self, class_id: str | None) -> datetime | None:
        if not class_id:
            return None
        klass = self.db.get(AcademicClass, class_id)
        if not klass:
            return None
        if klass.start_date:
            return klass.start_date
        if klass.block_id:
            block = self.db.get(AcademicBlock, klass.block_id)
            if block and block.start_date:
                return block.start_date
        if klass.term_id:
            term = self.db.get(AcademicTerm, klass.term_id)
            if term and term.start_date:
                return term.start_date
        return None

    def _synced_course_blocks_for_sessions(self, course_id: str) -> list[dict[str, Any]]:
        rows = (
            self.db.query(CourseSyncState)
            .filter(CourseSyncState.course_id == course_id)
            .order_by(CourseSyncState.created_at.asc(), CourseSyncState.block_id.asc())
            .all()
        )
        return [
            {
                'block_id': row.block_id,
                'type': row.block_type,
                'block_type': row.block_type,
                'display_name': row.display_name,
                'parent_block_id': row.parent_block_id,
                'children': [],
            }
            for row in rows
            if row.block_id
        ]

    def _session_build_has_components(self, result: dict[str, Any]) -> bool:
        return (
            int(result.get('session_count') or 0) > 0
            and (
                int(result.get('video_count') or 0) > 0
                or int(result.get('quiz_component_count') or 0) > 0
            )
        )

    async def ensure_session_structure_from_openedx(
        self,
        *,
        course_id: str,
        class_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Ensure one reusable course-level Bài/Session structure exists.

        Live Open edX blocks are authoritative. If the connector is temporarily
        unavailable, fall back to CourseSyncState so analytics can still rebuild
        from the latest course tree already synchronized into Dash CMS.
        """
        existing = (
            self.db.query(AnalyticsCourseSession)
            .filter(
                AnalyticsCourseSession.course_id == course_id,
                AnalyticsCourseSession.active.is_(True),
            )
            .order_by(AnalyticsCourseSession.session_index.asc())
            .all()
        )
        if existing and not force:
            component_count = sum(
                len((row.components_json or {}).get('components') or [])
                for row in existing
            )
            video_count = sum(int(row.total_videos or 0) for row in existing)
            return {
                'status': 'existing',
                'course_id': course_id,
                'session_count': len(existing),
                'component_count': component_count,
                'video_count': video_count,
                'source': 'analytics_course_sessions',
            }

        live_error: str | None = None
        clean_blocks: list[dict[str, Any]] = []
        try:
            blocks = await OpenEdxClient().get_course_blocks(course_id)
            clean_blocks = [item for item in (blocks or []) if isinstance(item, dict)]
        except Exception as exc:
            self.db.rollback()
            live_error = f'{type(exc).__name__}: {str(exc)[:800]}'

        course_start_at = self._course_start_at_for_class(class_id)

        if clean_blocks:
            try:
                live_result = self.rebuild_session_structure_from_blocks(
                    course_id=course_id,
                    blocks=clean_blocks,
                    course_start_at=course_start_at,
                )
                if self._session_build_has_components(live_result):
                    return {
                        **live_result,
                        'status': 'rebuilt',
                        'block_count': len(clean_blocks),
                        'course_start_at': course_start_at.isoformat() if course_start_at else None,
                        'source': 'openedx_live',
                    }
            except IntegrityError:
                # Another analytics worker may have created the same unique
                # course/session rows after our initial existence check.
                self.db.rollback()
                raced = (
                    self.db.query(AnalyticsCourseSession)
                    .filter(
                        AnalyticsCourseSession.course_id == course_id,
                        AnalyticsCourseSession.active.is_(True),
                    )
                    .all()
                )
                if raced:
                    return {
                        'status': 'existing_after_race',
                        'course_id': course_id,
                        'session_count': len(raced),
                        'component_count': sum(
                            len((row.components_json or {}).get('components') or [])
                            for row in raced
                        ),
                        'video_count': sum(int(row.total_videos or 0) for row in raced),
                        'source': 'analytics_course_sessions',
                    }
                raise

        # Fallback to the latest normalized tree already stored by Course Sync.
        synced_blocks = self._synced_course_blocks_for_sessions(course_id)
        if synced_blocks:
            try:
                fallback_result = self.rebuild_session_structure_from_blocks(
                    course_id=course_id,
                    blocks=synced_blocks,
                    course_start_at=course_start_at,
                )
                if int(fallback_result.get('session_count') or 0) > 0:
                    return {
                        **fallback_result,
                        'status': 'rebuilt_from_sync_state',
                        'block_count': len(synced_blocks),
                        'course_start_at': course_start_at.isoformat() if course_start_at else None,
                        'source': 'ai_course_sync_state',
                        'live_error': live_error,
                    }
            except IntegrityError:
                self.db.rollback()
                raced = (
                    self.db.query(AnalyticsCourseSession)
                    .filter(
                        AnalyticsCourseSession.course_id == course_id,
                        AnalyticsCourseSession.active.is_(True),
                    )
                    .all()
                )
                if raced:
                    return {
                        'status': 'existing_after_race',
                        'course_id': course_id,
                        'session_count': len(raced),
                        'component_count': sum(
                            len((row.components_json or {}).get('components') or [])
                            for row in raced
                        ),
                        'video_count': sum(int(row.total_videos or 0) for row in raced),
                        'source': 'analytics_course_sessions',
                    }
                raise

        if live_error:
            return {
                'status': 'fetch_failed',
                'course_id': course_id,
                'session_count': 0,
                'block_count': len(clean_blocks),
                'fallback_block_count': len(synced_blocks),
                'error': live_error,
            }
        if not clean_blocks and not synced_blocks:
            return {
                'status': 'no_blocks',
                'course_id': course_id,
                'session_count': 0,
                'block_count': 0,
                'fallback_block_count': 0,
            }
        return {
            'status': 'no_sessions',
            'course_id': course_id,
            'session_count': 0,
            'block_count': len(clean_blocks),
            'fallback_block_count': len(synced_blocks),
            'source': 'openedx_live_or_sync_state',
        }

    def rebuild_session_structure_from_blocks(
        self,
        *,
        course_id: str,
        blocks: list[dict[str, Any]],
        course_start_at: datetime | None = None,
    ) -> dict[str, Any]:
        mappings = build_session_mappings_from_blocks(
            course_id,
            blocks,
            course_start_at=course_start_at,
        )
        now = datetime.utcnow()
        saved = 0
        component_count = 0
        video_count = 0
        quiz_component_count = 0
        active_indices: set[int] = set()

        for mapping in mappings:
            active_indices.add(int(mapping.session_index))
            row = self.db.query(AnalyticsCourseSession).filter(
                AnalyticsCourseSession.course_id == course_id,
                AnalyticsCourseSession.session_index == mapping.session_index,
            ).first()
            if not row:
                row = AnalyticsCourseSession(
                    course_id=course_id,
                    session_index=mapping.session_index,
                    session_key=mapping.session_key,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(row)

            video_components = [item for item in mapping.components if item.block_type == 'video']
            quiz_components = [
                item for item in mapping.components
                if item.block_type in {'problem', 'quiz', 'sequential_quiz', 'library_content'}
            ]
            component_count += len(mapping.components)
            video_count += len(video_components)
            quiz_component_count += len(quiz_components)

            row.session_key = mapping.session_key
            row.session_title = mapping.session_title
            row.week_index = mapping.week_index
            row.deadline_at = mapping.deadline_at
            row.deadline_source = mapping.deadline_source
            row.deadline_mapping_quality = mapping.deadline_mapping_quality
            row.total_parts = len(video_components)
            row.total_videos = len(video_components)
            row.quiz_usage_key = mapping.quiz.usage_key if mapping.quiz else None
            row.components_json = {
                'components': [asdict(item) for item in mapping.components],
                'match_keys': list(dict.fromkeys(mapping.match_keys or [])),
            }
            row.session_type = mapping.session_type
            row.source = 'openedx_blocks_auto'
            row.active = True
            row.rebuilt_at = now
            row.updated_at = now
            saved += 1

        # If a course outline shrinks/changes, never leave removed sessions active.
        if mappings:
            stale_rows = (
                self.db.query(AnalyticsCourseSession)
                .filter(
                    AnalyticsCourseSession.course_id == course_id,
                    AnalyticsCourseSession.active.is_(True),
                    ~AnalyticsCourseSession.session_index.in_(sorted(active_indices)),
                )
                .all()
            )
            for row in stale_rows:
                row.active = False
                row.updated_at = now
                self.db.add(row)

        self.db.commit()
        return {
            'course_id': course_id,
            'session_count': len(mappings),
            'saved': saved,
            'component_count': component_count,
            'video_count': video_count,
            'quiz_component_count': quiz_component_count,
            'deadline_known_count': len([item for item in mappings if item.deadline_at is not None]),
            'deadline_pattern': [
                week_for_session(i, len(mappings) or 1)
                for i in range(1, len(mappings) + 1)
            ],
        }

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
            components_payload = r.components_json or {}
            components = components_payload.get('components', [])
            match_keys = components_payload.get('match_keys', [])
            if override:
                components = [dict(item) for item in components]
                for item in components:
                    if str(item.get('block_type') or '').lower() in {'problem', 'quiz', 'sequential_quiz', 'library_content'}:
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
                'match_keys': list(match_keys or []),
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

    @staticmethod
    def _video_quality_from_totals(
        completion_percent: float | None,
        watch_percent: float | None,
    ) -> tuple[float | None, float | None]:
        if completion_percent is None or watch_percent is None:
            return None, None
        completion = max(0.0, min(1.0, float(completion_percent) / 100.0))
        watch = max(0.0, min(1.0, float(watch_percent) / 100.0))
        consistency = max(0.0, 1.0 - abs(completion - watch))
        quality = min(completion, watch) * consistency
        return round(consistency * 100.0, 2), round(quality * 100.0, 2)

    @staticmethod
    def _video_event_is_new(
        event: AnalyticsTrackingEvent,
        *,
        last_loki_ts_ns: int,
        last_event_at: datetime | None,
    ) -> bool:
        if event.loki_ts_ns is not None and last_loki_ts_ns > 0:
            return int(event.loki_ts_ns) > last_loki_ts_ns
        if last_event_at is not None and event.event_time is not None:
            return event.event_time > last_event_at
        return last_loki_ts_ns <= 0 and last_event_at is None

    def recalculate_course_video_progress(self, *, course_id: str, username: str | None = None, class_id: str | None = None) -> dict[str, Any]:
        """Incrementally materialize video analytics.

        AnalyticsStudentVideoProgress is the durable cumulative state. Loki raw
        events are only the incremental input and may later be removed by the
        retention task without making historical progress decrease.
        """
        video_session_lookup = self._video_session_lookup(course_id=course_id)
        query = self.db.query(AnalyticsTrackingEvent).filter(
            AnalyticsTrackingEvent.course_id == course_id,
            AnalyticsTrackingEvent.event_type.in_(list(VIDEO_EVENT_TYPES)),
        )
        source_query = query
        identity: dict[str, Any] | None = None
        target_usernames: list[str] | None = None
        if class_id:
            identity = self._class_tracking_identity_maps(class_id=class_id, course_id=course_id)
            target_usernames = [username] if username else list(identity.get('ap_usernames') or [])
            if not target_usernames:
                return {
                    'course_id': course_id,
                    'class_id': class_id,
                    'username': username,
                    'video_progress_rows': 0,
                    'message': 'Lớp chưa có identity hợp lệ để tính video.',
                }
            query = self._apply_tracking_identity_filter(query, identity)
        elif username:
            target_usernames = [username]
            query = query.filter(AnalyticsTrackingEvent.username == username)

        events = query.order_by(
            AnalyticsTrackingEvent.event_time.asc(),
            AnalyticsTrackingEvent.loki_ts_ns.asc().nullslast(),
        ).all()
        grouped: dict[tuple[str, str], list[AnalyticsTrackingEvent]] = defaultdict(list)
        for ev in events:
            canonical = self._canonical_event_username(ev, identity)
            if not canonical or not ev.video_id:
                continue
            if target_usernames is not None and canonical not in set(target_usernames):
                continue
            grouped[(canonical, ev.video_id)].append(ev)

        now = datetime.utcnow()
        saved = 0
        skipped_no_new_events = 0
        session_mapping_backfilled = 0
        for (user, video_id), group in grouped.items():
            row = self.db.query(AnalyticsStudentVideoProgress).filter(
                AnalyticsStudentVideoProgress.course_id == course_id,
                AnalyticsStudentVideoProgress.username == user,
                AnalyticsStudentVideoProgress.video_id == video_id,
            ).first()
            evidence = dict(row.evidence_json or {}) if row else {}
            last_loki_ts_ns = int(evidence.get('last_loki_ts_ns') or 0)
            last_event_at = row.last_event_at if row else None
            new_group = [
                event
                for event in group
                if self._video_event_is_new(
                    event,
                    last_loki_ts_ns=last_loki_ts_ns,
                    last_event_at=last_event_at,
                )
            ]
            if row and not new_group:
                # Session structure may have been created after this cumulative
                # video row. Backfill session metadata even when there is no new
                # video event; otherwise old rows remain permanently unmapped.
                latest_existing = group[-1]
                matched_existing = self._match_video_session(
                    video_id=row.video_id,
                    video_code=row.video_code or latest_existing.video_code,
                    lookup=video_session_lookup,
                )
                if matched_existing:
                    session = matched_existing.get('session') or {}
                    component = matched_existing.get('component') or {}
                    next_session_key = session.get('session_key')
                    next_session_index = session.get('session_index')
                    next_title = component.get('title') or component.get('display_name') or row.component_title or ''
                    changed = (
                        row.session_key != next_session_key
                        or row.session_index != next_session_index
                        or row.component_title != next_title
                    )
                    if changed:
                        row.session_key = next_session_key
                        row.session_index = next_session_index
                        row.component_title = next_title
                        row.calculated_at = now
                        self.db.add(row)
                        saved += 1
                        session_mapping_backfilled += 1
                skipped_no_new_events += 1
                continue

            calculator_events: list[VideoEventInput] = []
            previous_state = evidence.get('last_event_state') if isinstance(evidence.get('last_event_state'), dict) else {}
            if row and previous_state and str(previous_state.get('event_type') or '') in {'play_video', 'edx.video.played'}:
                previous_time = self._as_datetime(previous_state.get('event_time'))
                if previous_time is not None:
                    calculator_events.append(VideoEventInput(
                        str(previous_state.get('event_type')),
                        previous_time,
                        previous_state.get('current_time_seconds'),
                        previous_state.get('duration_seconds'),
                        {},
                    ))
            calculator_events.extend(
                VideoEventInput(
                    e.event_type,
                    e.event_time,
                    e.current_time_seconds,
                    e.video_duration_seconds,
                    e.raw_event or {},
                )
                for e in new_group
            )
            result = calculate_video_progress(
                calculator_events,
                complete_threshold=getattr(settings, 'analytics_video_complete_threshold', 0.9),
                suspicious_watch_ratio=getattr(settings, 'analytics_suspicious_watch_ratio', 0.25),
                max_passive_segment_seconds=getattr(settings, 'analytics_max_passive_segment_seconds', 600),
            )

            if not row:
                row = AnalyticsStudentVideoProgress(
                    course_id=course_id,
                    username=user,
                    video_id=video_id,
                )
                self.db.add(row)

            latest = new_group[-1]
            matched_session = self._match_video_session(
                video_id=video_id,
                video_code=latest.video_code,
                lookup=video_session_lookup,
            )
            row.user_id = latest.user_id or row.user_id
            row.video_code = latest.video_code or row.video_code
            if matched_session:
                session = matched_session.get('session') or {}
                component = matched_session.get('component') or {}
                row.session_key = session.get('session_key')
                row.session_index = session.get('session_index')
                row.component_title = component.get('title') or component.get('display_name') or row.component_title or ''

            old_duration = float(row.duration_seconds or 0)
            new_duration = float(result.duration_seconds or 0)
            duration = max(old_duration, new_duration) or None
            old_position = float(row.max_position_seconds or 0)
            new_position = float(result.max_position_seconds or 0)
            max_position = max(old_position, new_position) if (old_position or new_position) else None
            completion = (
                round(max(0.0, min(100.0, (float(max_position) / float(duration)) * 100.0)), 2)
                if duration and max_position is not None
                else (row.completion_percent if row.completion_percent is not None else result.completion_percent)
            )

            cumulative_watch = round(float(row.estimated_watch_seconds or 0) + float(result.estimated_watch_seconds or 0), 2)
            watch_percent = (
                round(max(0.0, min(100.0, cumulative_watch / float(duration) * 100.0)), 2)
                if duration else None
            )
            consistency, quality = self._video_quality_from_totals(completion, watch_percent)

            actual_play_count = sum(1 for e in new_group if e.event_type in {'play_video', 'edx.video.played'})
            actual_pause_count = sum(1 for e in new_group if e.event_type in {'pause_video', 'edx.video.paused'})
            actual_stop_count = sum(1 for e in new_group if e.event_type in {'stop_video', 'edx.video.stopped'})
            actual_seek_count = sum(1 for e in new_group if e.event_type in {'seek_video', 'edx.video.position.changed'})

            row.duration_seconds = duration
            row.max_position_seconds = max_position
            row.completion_percent = completion
            row.estimated_watch_seconds = cumulative_watch
            row.estimated_watch_percent = watch_percent
            row.consistency_percent = consistency
            row.video_quality_percent = quality
            row.long_passive_segment_count = int(row.long_passive_segment_count or 0) + int(result.long_passive_segment_count or 0)
            row.long_passive_seconds = round(float(row.long_passive_seconds or 0) + float(result.long_passive_seconds or 0), 2)
            row.passive_watch_seconds = round(float(row.passive_watch_seconds or 0) + float(result.passive_watch_seconds or 0), 2)
            row.play_count = int(row.play_count or 0) + actual_play_count
            row.pause_count = int(row.pause_count or 0) + actual_pause_count
            row.stop_count = int(row.stop_count or 0) + actual_stop_count
            row.seek_count = int(row.seek_count or 0) + actual_seek_count

            cumulative_large_seek_count = int(evidence.get('large_seek_count') or 0) + int((result.evidence or {}).get('large_seek_count') or 0)
            reasons: list[str] = []
            if cumulative_large_seek_count:
                reasons.append('LARGE_SEEK_JUMP')
            if int(row.long_passive_segment_count or 0):
                reasons.append('LONG_PASSIVE_PLAYBACK')
            suspicious_watch_ratio = float(getattr(settings, 'analytics_suspicious_watch_ratio', 0.25) or 0.25)
            complete_threshold = float(getattr(settings, 'analytics_video_complete_threshold', 0.9) or 0.9)
            if duration and completion is not None and completion >= complete_threshold * 100.0 and cumulative_watch < float(duration) * suspicious_watch_ratio:
                reasons.append('HIGH_COMPLETION_LOW_WATCH_TIME')
            if int(row.play_count or 0) >= 3 and duration and cumulative_watch < min(30.0, float(duration) * 0.1):
                reasons.append('MANY_VIDEOS_COMPLETED_TOO_FAST')
            row.is_completed = bool(completion is not None and completion >= complete_threshold * 100.0)
            row.is_suspicious = bool([reason for reason in reasons if reason != 'LONG_PASSIVE_PLAYBACK'])
            row.suspicious_reason = ','.join(reasons)

            all_times = [e.event_time for e in new_group if e.event_time]
            if all_times:
                first_new = min(all_times)
                last_new = max(all_times)
                row.first_played_at = min([d for d in (row.first_played_at, first_new) if d])
                row.last_event_at = max([d for d in (row.last_event_at, last_new) if d])

            max_loki_ts_ns = max(
                [int(e.loki_ts_ns) for e in new_group if e.loki_ts_ns is not None]
                or [last_loki_ts_ns]
            )
            row.evidence_json = {
                **evidence,
                'segments': (result.evidence or {}).get('segments', []),
                'event_count': int(evidence.get('event_count') or 0) + len(new_group),
                'large_seek_count': cumulative_large_seek_count,
                'long_passive_segment_count': int(row.long_passive_segment_count or 0),
                'long_passive_seconds': row.long_passive_seconds,
                'passive_watch_seconds': row.passive_watch_seconds,
                'consistency_percent': row.consistency_percent,
                'video_quality_percent': row.video_quality_percent,
                'last_loki_ts_ns': max_loki_ts_ns,
                'last_event_state': {
                    'event_type': latest.event_type,
                    'event_time': latest.event_time.isoformat() if latest.event_time else None,
                    'current_time_seconds': latest.current_time_seconds,
                    'duration_seconds': latest.video_duration_seconds,
                },
                'materialization_mode': 'incremental_cumulative_v1',
            }
            row.calculated_at = now
            saved += 1

        self.db.commit()
        return {
            'course_id': course_id,
            'class_id': class_id,
            'username': username,
            'video_progress_rows': saved,
            'skipped_no_new_events': skipped_no_new_events,
            'session_mapping_backfilled': session_mapping_backfilled,
            'source_event_exists': bool(source_query.with_entities(AnalyticsTrackingEvent.id).first()),
            'matched_event_count': len(events),
            'identity_student_count': len(target_usernames or []),
            'identity_ambiguous_username_count': len((identity or {}).get('ambiguous_usernames') or []),
            'identity_ambiguous_user_id_count': len((identity or {}).get('ambiguous_user_ids') or []),
            'materialization_mode': 'incremental_cumulative_v1',
        }

    def recalculate_course_quiz_attempts(self, *, course_id: str, username: str | None = None, class_id: str | None = None) -> dict[str, Any]:
        """Materialize quiz attempts without overwriting retained history.

        Raw retention can remove old tracking rows. Existing attempts are matched
        by reset nonce or start timestamp; unmatched retained-window features are
        appended after the current max attempt number instead of reusing attempt
        number 1 and corrupting historical rows.
        """
        query = self.db.query(AnalyticsTrackingEvent).filter(
            AnalyticsTrackingEvent.course_id == course_id,
            AnalyticsTrackingEvent.event_type.in_(list(QUIZ_ANALYTICS_EVENT_TYPES)),
        )
        source_query = query
        identity: dict[str, Any] | None = None
        target_usernames: list[str] | None = None
        if class_id:
            identity = self._class_tracking_identity_maps(class_id=class_id, course_id=course_id)
            target_usernames = [username] if username else list(identity.get('ap_usernames') or [])
            if not target_usernames:
                return {
                    'course_id': course_id,
                    'class_id': class_id,
                    'username': username,
                    'quiz_attempt_rows': 0,
                    'message': 'Lớp chưa có identity hợp lệ để tính quiz.',
                }
            query = self._apply_tracking_identity_filter(query, identity)
        elif username:
            target_usernames = [username]
            query = query.filter(AnalyticsTrackingEvent.username == username)

        rows = query.order_by(
            AnalyticsTrackingEvent.event_time.asc(),
            AnalyticsTrackingEvent.loki_ts_ns.asc().nullslast(),
        ).all()
        normalized_events: list[EventLike] = []
        for raw in rows:
            canonical = self._canonical_event_username(raw, identity)
            if not canonical:
                continue
            if target_usernames is not None and canonical not in set(target_usernames):
                continue
            normalized_events.append(EventLike(
                event_type=raw.event_type,
                event_source=raw.event_source,
                event_time=raw.event_time,
                user_id=raw.user_id,
                username=canonical,
                course_id=raw.course_id,
                page_url=raw.page_url,
                raw_event=raw.raw_event or {},
                raw_context=raw.raw_context or {},
                raw_json=raw.raw_json or {},
            ))

        features = build_quiz_attempt_features(normalized_events)
        now = datetime.utcnow()
        saved = 0
        created = 0
        updated = 0

        existing_by_key: dict[tuple[str, str], list[AnalyticsQuizAttempt]] = defaultdict(list)
        existing_query = self.db.query(AnalyticsQuizAttempt).filter(AnalyticsQuizAttempt.course_id == course_id)
        if target_usernames is not None:
            existing_query = existing_query.filter(AnalyticsQuizAttempt.username.in_(target_usernames))
        for existing in existing_query.order_by(
            AnalyticsQuizAttempt.username.asc(),
            AnalyticsQuizAttempt.unit_usage_key.asc(),
            AnalyticsQuizAttempt.attempt_no.asc(),
        ).all():
            existing_by_key[(str(existing.username), str(existing.unit_usage_key))].append(existing)

        for feat in features:
            key = (str(feat.username), str(feat.unit_usage_key))
            candidates = existing_by_key.get(key, [])
            row: AnalyticsQuizAttempt | None = None

            if feat.unit_reset_nonce:
                row = next(
                    (
                        item for item in candidates
                        if str(item.unit_reset_nonce or '') == str(feat.unit_reset_nonce)
                    ),
                    None,
                )
            if row is None and feat.started_at is not None:
                row = next(
                    (
                        item for item in candidates
                        if item.started_at is not None and item.started_at == feat.started_at
                    ),
                    None,
                )

            if row is None:
                next_attempt_no = max([int(item.attempt_no or 0) for item in candidates] or [0]) + 1
                row = AnalyticsQuizAttempt(
                    course_id=feat.course_id,
                    username=feat.username,
                    unit_usage_key=feat.unit_usage_key,
                    attempt_no=next_attempt_no,
                )
                self.db.add(row)
                existing_by_key[key].append(row)
                created += 1
            else:
                updated += 1

            row.user_id = feat.user_id or row.user_id
            row.sequence_usage_key = feat.sequence_usage_key or row.sequence_usage_key
            row.unit_reset_nonce = feat.unit_reset_nonce or row.unit_reset_nonce
            if feat.started_at is not None:
                row.started_at = min([d for d in (row.started_at, feat.started_at) if d])
            if feat.ended_at is not None:
                row.ended_at = max([d for d in (row.ended_at, feat.ended_at) if d])
            row.reset_count = max(int(row.reset_count or 0), int(feat.reset_count or 0))
            row.submission_count = max(int(row.submission_count or 0), len(feat.submissions))

            assigned = list(dict.fromkeys([
                *(row.assigned_problem_usage_keys_json or []),
                *(feat.assigned_problem_usage_keys or []),
            ]))
            locations = list(dict.fromkeys([
                *(row.itembank_locations_json or []),
                *(feat.itembank_locations or []),
            ]))
            row.assigned_problem_usage_keys_json = assigned
            row.itembank_locations_json = locations

            if feat.score_earned is not None:
                row.score_earned = max(float(row.score_earned or 0), float(feat.score_earned))
            if feat.score_possible is not None:
                row.score_possible = max(float(row.score_possible or 0), float(feat.score_possible))
            if feat.median_time_per_question_seconds is not None:
                if row.median_time_per_question_seconds is None or len(feat.submissions) >= int(row.submission_count or 0):
                    row.median_time_per_question_seconds = feat.median_time_per_question_seconds
            if feat.repeat_rate is not None:
                row.repeat_rate = max(float(row.repeat_rate or 0), float(feat.repeat_rate))
            row.suspicious_quiz_speed = bool(row.suspicious_quiz_speed or feat.suspicious_quiz_speed)
            row.fishing_pattern = bool(row.fishing_pattern or feat.fishing_pattern)
            row.showanswer_count = max(int(row.showanswer_count or 0), int(feat.showanswer_count or 0))
            if feat.first_submission_at is not None:
                row.first_submission_at = min([d for d in (row.first_submission_at, feat.first_submission_at) if d])
            if feat.last_submission_at is not None:
                row.last_submission_at = max([d for d in (row.last_submission_at, feat.last_submission_at) if d])
            row.low_confidence_reason = feat.low_confidence_reason or row.low_confidence_reason
            row.evidence_json = {
                **(row.evidence_json or {}),
                **(feat.evidence or {}),
                'materialization_mode': 'retention_safe_upsert_v1',
            }
            row.calculated_at = now
            saved += 1

        self.db.commit()
        return {
            'course_id': course_id,
            'class_id': class_id,
            'username': username,
            'quiz_attempt_rows': saved,
            'created': created,
            'updated': updated,
            'source_event_exists': bool(source_query.with_entities(AnalyticsTrackingEvent.id).first()),
            'matched_event_count': len(rows),
            'normalized_event_count': len(normalized_events),
            'identity_student_count': len(target_usernames or []),
            'identity_ambiguous_username_count': len((identity or {}).get('ambiguous_usernames') or []),
            'identity_ambiguous_user_id_count': len((identity or {}).get('ambiguous_user_ids') or []),
            'materialization_mode': 'retention_safe_upsert_v1',
        }

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

    def _quiz_attempt_match_score(
        self,
        *,
        attempt: AnalyticsQuizAttempt,
        session: dict[str, Any],
    ) -> tuple[int, str | None]:
        """Return deterministic session match score for one quiz attempt.

        Production tracking can carry a stale sequence key while the unit key
        already points at the next/previous Bài. Prefer the most specific
        evidence observed in production:
        assigned problem > unit/vertical > sequence.
        """
        match_keys = [
            str(value)
            for value in (session.get('match_keys') or [])
            if value
        ]
        quiz_key = str(session.get('quiz_usage_key') or '')
        session_key = str(session.get('session_key') or '')
        components = session.get('components') if isinstance(session.get('components'), list) else []

        if quiz_key:
            match_keys.append(quiz_key)
        if session_key:
            match_keys.append(session_key)
        match_keys.extend(
            str(item.get('usage_key') or item.get('id') or '')
            for item in components
            if isinstance(item, dict)
        )
        match_keys = list(dict.fromkeys(key for key in match_keys if key))

        assigned = [
            str(value)
            for value in (attempt.assigned_problem_usage_keys_json or [])
            if value
        ]
        if any(
            self._key_match(value, key)
            for value in assigned
            for key in match_keys
        ):
            return 300, 'assigned_problem'

        if attempt.unit_usage_key and any(
            self._key_match(attempt.unit_usage_key, key)
            for key in match_keys
        ):
            return 200, 'unit'

        if attempt.sequence_usage_key and any(
            self._key_match(attempt.sequence_usage_key, key)
            for key in match_keys
        ):
            return 100, 'sequence'

        return 0, None

    @staticmethod
    def _quiz_attempt_representative_rank(attempt: AnalyticsQuizAttempt) -> tuple[int, int, datetime]:
        """Prefer submitted/scored evidence, then the latest attempt."""
        submitted = int(attempt.submission_count or 0)
        scored = 1 if attempt.score_earned is not None or attempt.score_possible is not None else 0
        when = (
            attempt.last_submission_at
            or attempt.first_submission_at
            or attempt.ended_at
            or attempt.started_at
            or datetime.min
        )
        return (1 if submitted > 0 else 0, scored, when)

    def _resolve_quiz_attempts_by_session(
        self,
        *,
        attempts: list[AnalyticsQuizAttempt],
        sessions: list[dict[str, Any]],
    ) -> tuple[dict[int, AnalyticsQuizAttempt], dict[str, Any]]:
        """Resolve every attempt to at most one Bài/Session.

        This prevents the same stale sequence/unit pair from being counted in
        two adjacent Bài. Equal top scores across multiple sessions remain
        unresolved rather than being guessed.
        """
        resolved: dict[int, AnalyticsQuizAttempt] = {}
        method_counts: Counter[str] = Counter()
        ambiguous = 0
        unmatched = 0

        for attempt in attempts:
            scored_sessions: list[tuple[int, int, str]] = []
            for session in sessions:
                session_index = int(session.get('session_index') or 0)
                if session_index <= 0:
                    continue
                score, method = self._quiz_attempt_match_score(
                    attempt=attempt,
                    session=session,
                )
                if score > 0 and method:
                    scored_sessions.append((score, session_index, method))

            if not scored_sessions:
                unmatched += 1
                continue

            max_score = max(item[0] for item in scored_sessions)
            winners = [item for item in scored_sessions if item[0] == max_score]
            winner_sessions = {item[1] for item in winners}
            if len(winner_sessions) != 1:
                ambiguous += 1
                continue

            _, session_index, method = winners[0]
            method_counts[method] += 1

            current = resolved.get(session_index)
            if current is None or self._quiz_attempt_representative_rank(attempt) > self._quiz_attempt_representative_rank(current):
                resolved[session_index] = attempt

        return resolved, {
            'attempt_count': len(attempts),
            'resolved_session_count': len(resolved),
            'match_method_counts': dict(method_counts),
            'ambiguous_attempt_count': ambiguous,
            'unmatched_attempt_count': unmatched,
        }


    def _class_tracking_identity_maps(self, *, class_id: str, course_id: str) -> dict[str, Any]:
        """Resolve AP roster identities to Open edX tracking identities.

        Derived analytics keeps AcademicStudent.username as the stable dashboard
        key, while raw tracking events are matched using OpenEdXUserMapping and
        AcademicStudentLearningSnapshot openedx_username/openedx_user_id.
        Ambiguous Open edX identities are deliberately excluded.
        """
        rows = (
            self.db.query(
                AcademicStudent.id,
                AcademicStudent.username,
                OpenEdXUserMapping.openedx_username,
                OpenEdXUserMapping.openedx_user_id,
                AcademicStudentLearningSnapshot.openedx_username,
                AcademicStudentLearningSnapshot.openedx_user_id,
            )
            .join(AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id)
            .outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id)
            .outerjoin(
                AcademicStudentLearningSnapshot,
                (AcademicStudentLearningSnapshot.student_id == AcademicStudent.id)
                & (AcademicStudentLearningSnapshot.class_id == class_id)
                & (AcademicStudentLearningSnapshot.openedx_course_id == course_id),
            )
            .filter(AcademicClassStudent.class_id == class_id)
            .all()
        )

        username_candidates: dict[str, set[str]] = defaultdict(set)
        user_id_candidates: dict[str, set[str]] = defaultdict(set)
        raw_usernames: set[str] = set()
        raw_user_ids: set[str] = set()
        ap_usernames: set[str] = set()

        for (
            _student_id,
            ap_username,
            mapped_username,
            mapped_user_id,
            snapshot_username,
            snapshot_user_id,
        ) in rows:
            ap = str(ap_username or '').strip()
            if not ap:
                continue
            ap_usernames.add(ap)

            for candidate in (snapshot_username, mapped_username, ap):
                raw = str(candidate or '').strip()
                if not raw:
                    continue
                raw_usernames.add(raw)
                username_candidates[raw.lower()].add(ap)

            for candidate in (snapshot_user_id, mapped_user_id):
                raw = str(candidate or '').strip()
                if not raw:
                    continue
                raw_user_ids.add(raw)
                user_id_candidates[raw].add(ap)

        username_to_ap = {
            key: next(iter(values))
            for key, values in username_candidates.items()
            if len(values) == 1
        }
        user_id_to_ap = {
            key: next(iter(values))
            for key, values in user_id_candidates.items()
            if len(values) == 1
        }

        return {
            'ap_usernames': sorted(ap_usernames),
            'raw_usernames': raw_usernames,
            'raw_user_ids': raw_user_ids,
            'username_to_ap': username_to_ap,
            'user_id_to_ap': user_id_to_ap,
            'ambiguous_usernames': sorted(key for key, values in username_candidates.items() if len(values) > 1),
            'ambiguous_user_ids': sorted(key for key, values in user_id_candidates.items() if len(values) > 1),
        }

    @staticmethod
    def _canonical_event_username(event: AnalyticsTrackingEvent, identity: dict[str, Any] | None) -> str | None:
        if identity is None:
            return str(event.username or '').strip() or None
        user_id = str(event.user_id or '').strip()
        if user_id:
            mapped = (identity.get('user_id_to_ap') or {}).get(user_id)
            if mapped:
                return str(mapped)
        username = str(event.username or '').strip()
        if username:
            mapped = (identity.get('username_to_ap') or {}).get(username.lower())
            if mapped:
                return str(mapped)
        return None

    @staticmethod
    def _apply_tracking_identity_filter(query: Any, identity: dict[str, Any]) -> Any:
        filters: list[Any] = []
        raw_usernames = sorted(identity.get('raw_usernames') or [])
        raw_user_ids = sorted(identity.get('raw_user_ids') or [])
        if raw_usernames:
            filters.append(AnalyticsTrackingEvent.username.in_(raw_usernames))
        if raw_user_ids:
            filters.append(AnalyticsTrackingEvent.user_id.in_(raw_user_ids))
        if not filters:
            return query.filter(False)
        return query.filter(or_(*filters))

    def _student_usernames_for_class(self, *, class_id: str | None, course_id: str, username: str | None = None) -> list[str]:
        if username:
            return [username]
        users: set[str] = set()
        if class_id:
            identity = self._class_tracking_identity_maps(class_id=class_id, course_id=course_id)
            return list(identity.get('ap_usernames') or [])
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


    def _events_count_by_username(self, *, course_id: str, usernames: list[str], class_id: str | None = None) -> dict[str, int]:
        if not usernames:
            return {}
        if class_id:
            identity = self._class_tracking_identity_maps(class_id=class_id, course_id=course_id)
            query = self.db.query(AnalyticsTrackingEvent).filter(
                AnalyticsTrackingEvent.course_id == course_id,
            )
            query = self._apply_tracking_identity_filter(query, identity)
            counts: Counter[str] = Counter()
            allowed = set(usernames)
            for event in query.all():
                canonical = self._canonical_event_username(event, identity)
                if canonical and canonical in allowed:
                    counts[canonical] += 1
            return dict(counts)
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

    def _quiz_attempts_by_username(self, *, course_id: str, usernames: list[str]) -> dict[str, list[AnalyticsQuizAttempt]]:
        if not usernames:
            return {}
        rows = (
            self.db.query(AnalyticsQuizAttempt)
            .filter(
                AnalyticsQuizAttempt.course_id == course_id,
                AnalyticsQuizAttempt.username.in_(usernames),
            )
            .all()
        )
        grouped: dict[str, list[AnalyticsQuizAttempt]] = defaultdict(list)
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
        # Quiz attempts are derived directly from tracking events and must not
        # depend on session-structure availability. Persist them first so a
        # course without rebuilt blocks can still expose useful quiz analytics.
        quiz_result = self.recalculate_course_quiz_attempts(
            course_id=course_id,
            username=username,
            class_id=class_id,
        )
        sessions = self.get_session_structure(course_id=course_id, class_id=class_id)
        if not sessions:
            return {
                'class_id': class_id,
                'course_id': course_id,
                'processed': 0,
                'sessions': 0,
                'quiz': quiz_result,
                'message': 'Chưa có cấu trúc Bài/Session. Quiz analytics đã được tính; hãy rebuild session structure để tính tiến độ theo Bài/Deadline.',
            }
        users = self._student_usernames_for_class(class_id=class_id, course_id=course_id, username=username)
        snapshots = self._learning_snapshots_by_username(class_id=class_id, course_id=course_id)
        academic_service = AcademicService(self.db)
        now = datetime.utcnow()
        saved = 0
        quiz_resolution_totals: Counter[str] = Counter()
        for user in users:
            quiz_attempts = self._quiz_attempts_for_user(course_id=course_id, username=user)
            quiz_attempt_by_session, quiz_resolution = self._resolve_quiz_attempts_by_session(
                attempts=quiz_attempts,
                sessions=sessions,
            )
            quiz_resolution_totals['attempt_count'] += int(quiz_resolution.get('attempt_count') or 0)
            quiz_resolution_totals['resolved_session_count'] += int(quiz_resolution.get('resolved_session_count') or 0)
            quiz_resolution_totals['ambiguous_attempt_count'] += int(quiz_resolution.get('ambiguous_attempt_count') or 0)
            quiz_resolution_totals['unmatched_attempt_count'] += int(quiz_resolution.get('unmatched_attempt_count') or 0)
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
                raw_attempt = quiz_attempt_by_session.get(session_index)
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
        return {
            'class_id': class_id,
            'course_id': course_id,
            'processed': len(users),
            'sessions': len(sessions),
            'session_progress_rows': saved,
            'quiz': quiz_result,
            'quiz_resolution': dict(quiz_resolution_totals),
        }

    def recalculate_learning_behavior(self, *, class_id: str | None, course_id: str, username: str | None = None) -> dict[str, Any]:
        self.recalculate_student_session_progress(class_id=class_id, course_id=course_id, username=username)
        users = self._student_usernames_for_class(class_id=class_id, course_id=course_id, username=username)
        if not users and username:
            users = [username]

        events_by_user = self._events_count_by_username(course_id=course_id, usernames=users, class_id=class_id)
        videos_by_user = self._video_progress_by_username(course_id=course_id, usernames=users)
        sessions_by_user = self._session_progress_by_username(course_id=course_id, usernames=users)
        quiz_attempts_by_user = self._quiz_attempts_by_username(course_id=course_id, usernames=users)

        now = datetime.utcnow()
        counts = Counter()
        for user in users:
            rows = videos_by_user.get(user, [])
            raw_events_count = int(events_by_user.get(user, 0) or 0)
            quiz_rows = quiz_attempts_by_user.get(user, [])
            cumulative_video_events = sum(
                int((row.evidence_json or {}).get('event_count') or 0)
                for row in rows
            )
            cumulative_quiz_signals = sum(
                int(row.submission_count or 0)
                + int(row.showanswer_count or 0)
                + int(row.reset_count or 0)
                + (1 if row.started_at else 0)
                for row in quiz_rows
            )
            # Raw retention intentionally removes materialized video/quiz events.
            # Keep behavior confidence monotonic by using durable aggregates as
            # the minimum historical signal count.
            events_count = max(
                raw_events_count,
                cumulative_video_events + cumulative_quiz_signals,
            )
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
            suspicious_quiz_speed = len([r for r in quiz_rows if r.suspicious_quiz_speed])
            fishing_pattern = len([r for r in quiz_rows if r.fishing_pattern])
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
                total_quiz_sessions=len({str(r.unit_usage_key or '') for r in quiz_rows if r.unit_usage_key}),
                total_quiz_attempts=len(quiz_rows),
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
            snap.evidence_json = {
                **result.evidence,
                'raw_retained_event_count': raw_events_count,
                'cumulative_video_event_count': cumulative_video_events,
                'cumulative_quiz_signal_count': cumulative_quiz_signals,
                'deadline_known_sessions': len(deadline_known),
                'on_time_sessions': on_time,
                'late_sessions': late,
                'quiz_before_video_count': quiz_before,
                'learning_session_count': len(learning_session_rows),
                'session_types_excluded': len(session_rows) - len(learning_session_rows),
                'raw_retention_safe': True,
            }
            snap.last_activity_at = inp.last_activity_at
            snap.calculated_at = now
            counts[result.classification] += 1
        self.db.commit()
        return {'class_id': class_id, 'course_id': course_id, 'processed': len(users), 'counts': dict(counts)}



    def _class_matches_rollout(self, cls: AcademicClass | None, course_id: str | None = None) -> tuple[bool, list[str]]:
        """Check env-only rollout scope; does not require new tables."""
        reasons: list[str] = []
        mode = str(getattr(settings, 'analytics_rollout_mode', 'production') or 'production').strip().lower()
        if mode not in {'pilot', 'production'}:
            mode = 'production'
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
        mode = str(getattr(settings, 'analytics_rollout_mode', 'production') or 'production').strip().lower()
        if mode not in {'pilot', 'production'}:
            mode = 'production'
        enabled = True
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
            'ready_for_rollout': monitoring_status in {'OK', 'WARNING'} and True,
            'scheduler_enabled': True,
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

        if not ingest.get('file_exists'):
            issues.append({'severity': 'error', 'code': 'TRACKING_LOG_NOT_MOUNTED', 'message': 'Chưa thấy tracking.log trong container AI Server.', 'action': 'Mount thư mục Tutor LMS logs dạng read-only vào /openedx-data/lms/logs.'})
        if int(ingest.get('total_events_inserted') or 0) <= 0:
            issues.append({'severity': 'warning', 'code': 'NO_TRACKING_EVENTS_INGESTED', 'message': 'Chưa có event tracking nào được ingest.', 'action': 'Kiểm tra beat/worker hoặc chạy ingest thủ công.'})
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
        return {
            'allowed': not recent,
            'enabled': True,
            'cooldown_seconds': cooldown_seconds,
            'last_run_at': cp.last_run_at.isoformat() if cp and cp.last_run_at else None,
            'reasons': ['RECENT_INGEST_RUN'] if recent else [],
            'message': 'Có thể ingest.' if not recent else 'Ingest vừa chạy gần đây, hãy kiểm tra /jobs hoặc trạng thái ingest.',
            'safe_policy': 'signals_only_not_violation',
        }

    def _production_readiness_issue(
        self,
        *,
        code: str,
        severity: str,
        category: str,
        message: str,
        action: str,
        command: str | None = None,
        source: str = 'analytics',
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sev = str(severity or 'WARNING').upper()
        if sev in {'ERROR', 'CRITICAL'}:
            sev = 'BLOCKER'
        if sev not in {'BLOCKER', 'WARNING', 'INFO'}:
            sev = 'WARNING'
        return {
            'code': code,
            'severity': sev,
            'category': category,
            'message': message,
            'action': action,
            'command': command,
            'source': source,
            'blocking': sev == 'BLOCKER',
            'details': details or {},
        }

    def _normalize_production_issue(
        self,
        raw: dict[str, Any],
        *,
        default_category: str,
        source: str,
    ) -> dict[str, Any]:
        code = str(raw.get('code') or raw.get('key') or raw.get('message') or 'UNKNOWN_CHECK')
        severity = str(raw.get('severity') or 'WARNING').upper()
        if severity == 'ERROR':
            severity = 'BLOCKER'
        # Data-quality errors are often class/data gaps, not infrastructure
        # blockers. Keep the final production gate strict for platform health,
        # but do not block production just because a fresh class has no snapshot
        # yet; roster fallback and the post-ingest orchestrator handle warm-up.
        data_gap_codes = {
            'NO_BEHAVIOR_SNAPSHOT',
            'NO_BEHAVIOR_SNAPSHOTS',
            'MISSING_SESSION_STRUCTURE',
            'NO_CLASS_STUDENTS',
            'MISSING_COURSE_MAPPING',
            'CLASS_NOT_FOUND',
            'NO_VIDEO_PROGRESS_SNAPSHOT',
            'NO_TRACKING_EVENTS_INGESTED',
        }
        if code in data_gap_codes and source in {'data_quality', 'rollout', 'monitoring'}:
            severity = 'WARNING'
        return self._production_readiness_issue(
            code=code,
            severity=severity,
            category=str(raw.get('category') or default_category),
            message=str(raw.get('message') or code),
            action=str(raw.get('action') or 'Kiểm tra cấu hình hoặc dữ liệu liên quan.'),
            command=raw.get('command'),
            source=source,
            details={k: v for k, v in raw.items() if k not in {'code', 'key', 'severity', 'category', 'message', 'action', 'command'}},
        )

    def _dedupe_production_issues(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        severity_rank = {'BLOCKER': 3, 'WARNING': 2, 'INFO': 1}
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for item in issues:
            code = str(item.get('code') or 'UNKNOWN_CHECK')
            category = str(item.get('category') or 'Khác')
            key = (category, code)
            existing = merged.get(key)
            if not existing or severity_rank.get(str(item.get('severity')).upper(), 0) > severity_rank.get(str(existing.get('severity')).upper(), 0):
                merged[key] = dict(item)
            elif existing:
                sources = set(str(x) for x in str(existing.get('source') or '').split(',') if x)
                if item.get('source'):
                    sources.add(str(item.get('source')))
                if sources:
                    existing['source'] = ','.join(sorted(sources))
        return sorted(
            merged.values(),
            key=lambda i: (
                0 if str(i.get('severity')).upper() == 'BLOCKER' else 1 if str(i.get('severity')).upper() == 'WARNING' else 2,
                str(i.get('category') or ''),
                str(i.get('code') or ''),
            ),
        )

    def production_readiness_report(self, *, allowed_class_ids: set[str] | None = None) -> dict[str, Any]:
        """Final production gate for analytics.

        v25.9.16.7.2.64.13 changes the gate from a vague counter into an
        actionable operations checklist. Blockers are reserved for platform
        configuration/runtime problems. Data warm-up gaps such as no snapshots
        yet are warnings, because roster fallback and post-ingest recalculation
        keep the product usable while evidence accumulates.
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

        max_active_jobs = int(getattr(settings, 'analytics_backfill_max_active_jobs', 20) or 20)
        post_ingest_enabled = True
        scheduler_enabled = True
        ingest_enabled = True
        file_exists = bool(ingest.get('file_exists'))
        rollout_enabled = bool(rollout.get('enabled'))
        min_events = int(getattr(settings, 'analytics_production_min_events', 1) or 1)
        min_snapshots = int(getattr(settings, 'analytics_production_min_snapshots', 1) or 1)

        issues: list[dict[str, Any]] = []

        # Environment / runtime blockers.
        if not file_exists:
            issues.append(self._production_readiness_issue(
                code='TRACKING_LOG_NOT_MOUNTED',
                severity='BLOCKER',
                category='Tracking log',
                message='Container AI Server chưa thấy tracking.log Open edX.',
                action='Mount thư mục Tutor LMS logs dạng read-only vào backend/worker/beat và chạy analytics-tracking-log-doctor.sh.',
                command='cd /opt/ai-server && ./scripts/analytics-tracking-log-doctor.sh',
                source='ingest',
                details={'tracking_log_path': ingest.get('file_path') or getattr(settings, 'openedx_tracking_log_path', None)},
            ))
        if not rollout_enabled:
            issues.append(self._production_readiness_issue(
                code='ANALYTICS_ROLLOUT_DISABLED',
                severity='BLOCKER',
                category='Rollout',
                message='Rollout học online đang tắt.',
                action='Đặt ANALYTICS_ROLLOUT_MODE=pilot hoặc production trước khi công bố.',
                command='grep -n "ANALYTICS_ROLLOUT" .env.production',
                source='rollout',
                details={'rollout_mode': rollout.get('mode')},
            ))

        # Data warm-up warnings. These explain why UI has little/no data but do
        # not falsely say the whole production platform is broken.
        if event_count < min_events:
            issues.append(self._production_readiness_issue(
                code='NO_TRACKING_EVENTS_INGESTED',
                severity='WARNING' if file_exists and ingest_enabled else 'BLOCKER',
                category='Dữ liệu học online',
                message='Chưa có tracking event được ingest.',
                action='Chạy ingest hoặc chờ scheduler ingest. Đây là thiếu dữ liệu, không phải lỗi lớp rỗng.',
                command='curl -sS https://api-ai.cms-test.poly.edu.vn/api/health/analytics | jq',
                source='events',
                details={'tracking_event_count': int(event_count or 0), 'min_events': min_events},
            ))
        if snapshot_count < min_snapshots:
            issues.append(self._production_readiness_issue(
                code='NO_BEHAVIOR_SNAPSHOTS',
                severity='WARNING',
                category='Snapshot nhận định',
                message='Chưa có snapshot nhận định học online đủ ngưỡng production.',
                action='Dùng doctor lớp hoặc post-ingest orchestrator để tính dần. UI vẫn phải hiển thị roster AP với trạng thái Chưa đủ dữ liệu.',
                command='Mở /analytics/learning → chọn lớp → Kiểm tra dữ liệu lớp hoặc Tính lại lớp này',
                source='snapshots',
                details={'behavior_snapshot_count': int(snapshot_count or 0), 'min_snapshots': min_snapshots},
            ))
        if active_jobs > max_active_jobs:
            issues.append(self._production_readiness_issue(
                code='TOO_MANY_ACTIVE_ANALYTICS_JOBS',
                severity='WARNING',
                category='Worker jobs',
                message='Đang có nhiều job học online chạy cùng lúc.',
                action='Chờ job hoàn tất trước khi backfill thêm hoặc tăng worker có kiểm soát.',
                command='Mở /jobs và lọc learning_analytics_recalculate',
                source='jobs',
                details={'active_jobs': int(active_jobs or 0), 'max_active_jobs': max_active_jobs},
            ))
        if rollout_enabled and int((rollout.get('counters') or {}).get('in_rollout') or 0) <= 0:
            issues.append(self._production_readiness_issue(
                code='NO_CLASS_IN_ROLLOUT_SCOPE',
                severity='WARNING',
                category='Rollout',
                message='Chưa có lớp nào trong phạm vi rollout.',
                action='Kiểm tra allowlist campus/class/course hoặc mở rộng rollout mode.',
                command='grep -n "ANALYTICS_ROLLOUT" .env.production',
                source='rollout',
            ))
        if monitoring.get('monitoring_status') == 'BLOCKED':
            issues.append(self._production_readiness_issue(
                code='ANALYTICS_MONITORING_BLOCKED',
                severity='BLOCKER',
                category='Monitoring',
                message='Monitoring phát hiện blocker runtime cho học online.',
                action='Xem stuck job, mount log hoặc snapshot stale trong /analytics/learning và /jobs.',
                command='curl -sS https://api-ai.cms-test.poly.edu.vn/api/analytics/ops/monitoring | jq',
                source='monitoring',
                details={'monitoring_status': monitoring.get('monitoring_status')},
            ))

        for item in data_quality.get('issues') or []:
            issues.append(self._normalize_production_issue(item, default_category='Chất lượng dữ liệu', source='data_quality'))
        for item in rollout.get('issues') or []:
            issues.append(self._normalize_production_issue(item, default_category='Rollout', source='rollout'))
        for item in monitoring.get('issues') or []:
            issues.append(self._normalize_production_issue(item, default_category='Monitoring', source='monitoring'))

        issues = self._dedupe_production_issues(issues)
        blockers = [i for i in issues if str(i.get('severity')).upper() == 'BLOCKER']
        warnings = [i for i in issues if str(i.get('severity')).upper() == 'WARNING']
        infos = [i for i in issues if str(i.get('severity')).upper() == 'INFO']
        blocker_count = len(blockers)
        warning_count = len(warnings)
        ready = blocker_count == 0
        stage_status = 'BLOCKED' if blocker_count else ('READY_WITH_WARNINGS' if warning_count else 'READY')
        readiness = 'PRODUCTION_READY' if stage_status == 'READY' else ('PRODUCTION_READY_WITH_WARNINGS' if stage_status == 'READY_WITH_WARNINGS' else 'NOT_READY')
        primary_blocker = blockers[0] if blockers else None

        categories = ['Tracking log', 'Scheduler', 'Analytics Orchestrator', 'Worker jobs', 'Dữ liệu học online', 'Snapshot nhận định', 'Rollout', 'Monitoring', 'Chất lượng dữ liệu']
        section_items: list[dict[str, Any]] = []
        by_category = defaultdict(list)
        for issue in issues:
            by_category[str(issue.get('category') or 'Khác')].append(issue)
        for category in categories + sorted(k for k in by_category.keys() if k not in categories):
            category_issues = by_category.get(category, [])
            if not category_issues:
                section_items.append({'category': category, 'status': 'OK', 'blocker_count': 0, 'warning_count': 0, 'issues': []})
                continue
            section_blockers = [i for i in category_issues if str(i.get('severity')).upper() == 'BLOCKER']
            section_warnings = [i for i in category_issues if str(i.get('severity')).upper() == 'WARNING']
            section_items.append({
                'category': category,
                'status': 'BLOCKED' if section_blockers else ('WARNING' if section_warnings else 'INFO'),
                'blocker_count': len(section_blockers),
                'warning_count': len(section_warnings),
                'issues': category_issues,
            })

        checks = {
            'tracking_log_mounted': file_exists,
            'ingest_enabled': ingest_enabled,
            'scheduler_enabled': scheduler_enabled,
            'post_ingest_recalculate_enabled': post_ingest_enabled,
            'tracking_event_count': int(event_count or 0),
            'behavior_snapshot_count': int(snapshot_count or 0),
            'active_recalculate_jobs': int(active_jobs or 0),
            'max_active_recalculate_jobs': max_active_jobs,
            'data_quality_readiness': data_quality.get('readiness'),
            'rollout_enabled': rollout_enabled,
            'rollout_status': rollout.get('rollout_status'),
            'rollout_mode': rollout.get('mode'),
            'rollout_in_scope_classes': (rollout.get('counters') or {}).get('in_rollout', 0),
            'monitoring_status': monitoring.get('monitoring_status'),
            'stuck_analytics_job_count': monitoring.get('stuck_analytics_job_count'),
            'stale_snapshot_count': monitoring.get('stale_snapshot_count'),
        }

        next_actions = []
        seen_actions: set[str] = set()
        for item in blockers + warnings:
            action = str(item.get('action') or '').strip()
            if action and action not in seen_actions:
                seen_actions.add(action)
                next_actions.append(action)

        return {
            'version': getattr(settings, 'app_version', '25.9.16.7.2.64.13'),
            'ready_for_production': ready,
            'readiness': readiness,
            'stage_status': stage_status,
            'summary_label': 'Sẵn sàng production' if stage_status == 'READY' else ('Có thể pilot, còn cảnh báo' if stage_status == 'READY_WITH_WARNINGS' else 'Chưa sẵn sàng production'),
            'message': 'Không còn blocker production.' if ready else f'Cần xử lý blocker: {primary_blocker.get("code") if primary_blocker else "UNKNOWN"}.',
            'blocker_count': blocker_count,
            'warning_count': warning_count,
            'info_count': len(infos),
            'issue_count': len(issues),
            'primary_blocker': primary_blocker,
            'blockers': blockers,
            'warnings': warnings,
            'infos': infos,
            'issues': issues,
            'sections': section_items,
            'checks': checks,
            'rollout_control': rollout,
            'monitoring': monitoring,
            'data_quality': data_quality,
            'next_actions': next_actions,
            'can_pilot': ready,
            'can_broad_rollout': stage_status == 'READY',
            'safe_policy': 'signals_only_not_violation',
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm. Thiếu snapshot là trạng thái dữ liệu, không phải kết luận lớp rỗng.',
        }


    def analytics_sla_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_operations_workflow().analytics_sla_report(*args, **kwargs)




    def pilot_acceptance_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_operations_workflow().pilot_acceptance_report(*args, **kwargs)



    def analytics_uat_evidence_pack(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_operations_workflow().analytics_uat_evidence_pack(*args, **kwargs)



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
            'scheduler_enabled': True,
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
        """Use the same effective physical Course mapping as Student/Teacher Ops."""
        if preferred_course_id:
            return preferred_course_id
        if not class_id:
            return None
        cls = self.db.query(AcademicClass).filter(AcademicClass.id == class_id).first()
        if not cls:
            return None
        mapping = AcademicService(self.db).effective_course_mapping_for_class(cls)
        course_id = str(getattr(mapping, 'openedx_course_id', '') or '').strip() if mapping else ''
        return course_id or None

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
                'email': mask_email(item.email),
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

    def learning_dashboard(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().learning_dashboard(*args, **kwargs)


    def export_learning_behavior_csv(self, *args: Any, **kwargs: Any) -> str:
        return self._analytics_results_workflow().export_learning_behavior_csv(*args, **kwargs)


    def video_students(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().video_students(*args, **kwargs)


    def student_behavior_detail(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().student_behavior_detail(*args, **kwargs)


    def class_behavior_overview(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().class_behavior_overview(*args, **kwargs)


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
            score = self._subject_mapping_score_for_class(row, cls)
            if score is None:
                continue
            add_candidate(
                row.openedx_course_id,
                'subject_term_mapping',
                score,
                row,
                'Mapping kế thừa theo môn/kỳ/cơ sở/hệ.',
            )

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

    def analytics_course_class_mapping_reliability_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().analytics_course_class_mapping_reliability_report(*args, **kwargs)


    def class_result_doctor(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().class_result_doctor(*args, **kwargs)


    def behavior_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().behavior_summary(*args, **kwargs)


    def behavior_rows(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._analytics_results_workflow().behavior_rows(*args, **kwargs)
