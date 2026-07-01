from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import AcademicClass, AcademicClassCourseMapping, AcademicClassStudent, AcademicClassSyncJob, AcademicQuizDeadlineOverride, AcademicStudent, AcademicStudentLearningSnapshot
from app.models.learning_analytics import (
    AnalyticsCourseSession,
    AnalyticsIngestCheckpoint,
    AnalyticsLearningBehaviorSnapshot,
    AnalyticsStudentSessionProgress,
    AnalyticsStudentVideoProgress,
    AnalyticsTrackingEvent,
)
from app.services.learning_analytics.learning_behavior_classifier import BehaviorInput, classify_learning_behavior
from app.services.learning_analytics.session_deadline_mapper import build_session_mappings_from_blocks, week_for_session
from app.services.academic_service import AcademicService
from app.services.learning_analytics.tracking_event_parser import TrackingParseError, parse_tracking_log_line
from app.services.learning_analytics.tracking_log_reader import TrackingLogReader
from app.services.learning_analytics.video_watch_calculator import VideoEventInput, calculate_video_progress

VIDEO_EVENT_TYPES = {'play_video', 'pause_video', 'stop_video', 'seek_video', 'edx.video.position.changed'}
PROBLEM_EVENT_TYPES = {'problem_check', 'problem_graded', 'problem_save'}


class LearningAnalyticsCoreService:
    def __init__(self, db: Session):
        self.db = db

    def schema_inspect(self) -> dict[str, Any]:
        """Phase 0 report: what is reused and what the analytics core adds."""
        return {
            'version': '25.9.16.7.2',
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

    def _get_checkpoint(self, key: str, file_path: str) -> AnalyticsIngestCheckpoint:
        cp = self.db.query(AnalyticsIngestCheckpoint).filter(AnalyticsIngestCheckpoint.checkpoint_key == key).first()
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

    def run_ingest(self, *, file_path: str | None = None, max_lines: int | None = None) -> dict[str, Any]:
        if not bool(getattr(settings, 'analytics_ingest_enabled', True)):
            return {'enabled': False, 'status': 'disabled', 'message': 'ANALYTICS_INGEST_ENABLED=false'}
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
            if parsed.event_type in VIDEO_EVENT_TYPES:
                stats['video_events'] += 1
            if parsed.event_type in PROBLEM_EVENT_TYPES:
                stats['problem_events'] += 1
            try:
                if (stats['events_inserted'] % 500) == 0:
                    self.db.flush()
            except IntegrityError:
                self.db.rollback()
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
        cp.stats_json = {**dict(stats), 'event_type_counts': dict(event_type_counts), 'start_offset': result.start_offset, 'end_offset': result.end_offset, 'rotated': result.rotated}
        self.db.commit()
        return {'enabled': True, 'status': 'completed', 'file_path': path, 'file_exists': True, 'last_offset': result.end_offset, **cp.stats_json}

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

    def _student_usernames_for_class(self, *, class_id: str | None, course_id: str, username: str | None = None) -> list[str]:
        if username:
            return [username]
        users: set[str] = set()
        if class_id:
            rows = self.db.query(AcademicStudent).join(AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id).filter(AcademicClassStudent.class_id == class_id).all()
            users.update(str(row.username) for row in rows if row.username)
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
        snapshots = self._learning_snapshots_by_username(class_id=class_id, course_id=course_id)
        academic_service = AcademicService(self.db)
        now = datetime.utcnow()
        saved = 0
        for user in users:
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
                quiz_item = self._quiz_item_for_session(components=components, session_index=session_index, academic_service=academic_service)
                quiz_score = None
                quiz_attempted = False
                quiz_completed = False
                quiz_submitted_at = None
                if quiz_item:
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
                reason_codes: list[str] = []
                if not deadline_at:
                    reason_codes.append('MISSING_DEADLINE_MAPPING')
                if quiz_submitted_at and first_video_at and quiz_submitted_at < first_video_at:
                    reason_codes.append('QUIZ_BEFORE_VIDEO')
                if any(r.is_suspicious for r in rows):
                    reason_codes.extend([code for r in rows for code in str(r.suspicious_reason or '').split(',') if code])
                completed_before_deadline: bool | None = None
                completed_late: bool | None = None
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
                elif 'QUIZ_BEFORE_VIDEO' in reason_codes or any(code in reason_codes for code in ('HIGH_COMPLETION_LOW_WATCH_TIME', 'LARGE_SEEK_JUMP')):
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
                row.total_videos = total_videos
                row.videos_seen = videos_seen
                row.videos_completed = videos_completed
                row.avg_video_completion_percent = avg_completion
                row.estimated_watch_seconds = watch_seconds
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
                    'video_count': len(rows),
                }
                row.calculated_at = now
                saved += 1
        self.db.commit()
        return {'class_id': class_id, 'course_id': course_id, 'processed': len(users), 'sessions': len(sessions), 'session_progress_rows': saved}

    def recalculate_learning_behavior(self, *, class_id: str | None, course_id: str, username: str | None = None) -> dict[str, Any]:
        self.recalculate_student_session_progress(class_id=class_id, course_id=course_id, username=username)
        video_q = self.db.query(AnalyticsStudentVideoProgress).filter(AnalyticsStudentVideoProgress.course_id == course_id)
        if username:
            video_q = video_q.filter(AnalyticsStudentVideoProgress.username == username)
        video_rows = video_q.all()
        users = self._student_usernames_for_class(class_id=class_id, course_id=course_id, username=username)
        if not users and username:
            users = [username]
        now = datetime.utcnow()
        counts = Counter()
        for user in users:
            rows = [v for v in video_rows if v.username == user]
            events_count = self.db.query(AnalyticsTrackingEvent).filter(AnalyticsTrackingEvent.course_id == course_id, AnalyticsTrackingEvent.username == user).count()
            session_rows = self.db.query(AnalyticsStudentSessionProgress).filter(AnalyticsStudentSessionProgress.course_id == course_id, AnalyticsStudentSessionProgress.username == user).all()
            completed = [r for r in rows if r.is_completed]
            suspicious = [r for r in rows if r.is_suspicious]
            avg_completion = round(sum([r.completion_percent or 0 for r in rows]) / len(rows), 2) if rows else None
            avg_watch = round(sum([r.estimated_watch_percent or 0 for r in rows]) / len(rows), 2) if rows else None
            deadline_known = [r for r in session_rows if r.deadline_at]
            on_time = len([r for r in session_rows if r.completed_before_deadline is True])
            late = len([r for r in session_rows if r.completed_late is True])
            quiz_before = len([r for r in session_rows if 'QUIZ_BEFORE_VIDEO' in (r.reason_codes or [])])
            crammed = 0
            late_completion_dates = [r.last_activity_at.date() for r in session_rows if r.last_activity_at and r.completed_late]
            if late_completion_dates:
                crammed = max(Counter(late_completion_dates).values()) if late_completion_dates else 0
                crammed = crammed if crammed >= 3 else 0
            inp = BehaviorInput(
                total_events=events_count,
                total_sessions=len(session_rows) or len({r.session_index for r in rows if r.session_index}) or 0,
                sessions_started=len([r for r in session_rows if r.started_at]) or len({r.session_index for r in rows if r.session_index}) or (1 if rows else 0),
                sessions_completed_on_time=on_time,
                sessions_completed_late=late,
                crammed_session_count=crammed,
                quiz_before_video_count=quiz_before,
                video_before_quiz_count=len([r for r in session_rows if r.quiz_attempted and 'QUIZ_BEFORE_VIDEO' not in (r.reason_codes or [])]),
                total_videos_seen=len(rows),
                total_videos_completed=len(completed),
                avg_video_completion_percent=avg_completion,
                total_estimated_watch_seconds=sum([r.estimated_watch_seconds or 0 for r in rows]),
                avg_estimated_watch_percent=avg_watch,
                suspicious_video_count=len(suspicious),
                missing_duration_count=len([r for r in rows if not r.duration_seconds]),
                missing_session_mapping=any(r.session_index is None for r in rows) if rows else bool(not session_rows),
                missing_deadline_mapping=bool(session_rows and len(deadline_known) < len(session_rows)),
                last_activity_at=max([d for d in [r.last_activity_at for r in session_rows] + [r.last_event_at for r in rows] if d] or [None]),
                extra_reasons=[code for r in suspicious for code in (r.suspicious_reason or '').split(',') if code] + [code for sr in session_rows for code in (sr.reason_codes or []) if code],
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
            snap.display_label = result.display_label
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
            snap.evidence_json = {**result.evidence, 'deadline_known_sessions': len(deadline_known), 'on_time_sessions': on_time, 'late_sessions': late, 'quiz_before_video_count': quiz_before}
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
            'version': '25.9.16.7.2',
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
            'version': '25.9.16.7.2',
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
            'version': '25.9.16.7.2',
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
                reasons.append('MISSING_SESSION_STRUCTURE')
            if mapped_course_id and student_count > 0 and behavior_count < student_count:
                reasons.append('MISSING_OR_PARTIAL_BEHAVIOR_SNAPSHOT')
            if active_job:
                reasons.append('JOB_ALREADY_ACTIVE')
            can_enqueue = bool(mapped_course_id and student_count > 0 and session_count > 0 and not active_job)
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
            })
        return {
            'status': 'ok',
            'version': '25.9.16.7.2',
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
            'version': '25.9.16.7.2',
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
            if classifications.get('POSSIBLE_CHEATING', 0):
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
            'version': '25.9.16.7.2',
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
            'version': '25.9.16.7.2',
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
            q = q.filter(AnalyticsLearningBehaviorSnapshot.classification == classification)
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
        if preferred_course_id:
            return preferred_course_id
        if not class_id:
            return None
        mapping = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id == class_id,
            AcademicClassCourseMapping.active.is_(True),
        ).first()
        return mapping.openedx_course_id if mapping else None

    def _class_student_usernames(self, class_id: str | None) -> set[str]:
        if not class_id:
            return set()
        rows = self.db.query(AcademicStudent.username).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).filter(AcademicClassStudent.class_id == class_id).all()
        return {str(row[0]) for row in rows if row and row[0]}

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
                'possible_suspicious_count': cc.get('POSSIBLE_CHEATING', 0),
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
            'possible_suspicious_count': counts.get('POSSIBLE_CHEATING', 0),
            'insufficient_data_count': counts.get('INSUFFICIENT_DATA', 0),
            'normal_count': counts.get('NORMAL', 0),
            'data_quality_breakdown': dict(quality),
            'class_items': class_items[:limit],
            'top_possible_suspicious': [row_item(r) for r in top_suspicious if r.classification == 'POSSIBLE_CHEATING' or (r.suspicious_score or 0) > 0],
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

    def behavior_summary(self, *, class_id: str | None, course_id: str | None = None) -> dict[str, Any]:
        q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if class_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if course_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)
        rows = q.all()
        counts = Counter(r.classification for r in rows)
        quality = Counter(r.data_quality for r in rows)
        return {
            'total_students': len(rows),
            'likely_real_learning_count': counts.get('LIKELY_REAL_LEARNING', 0),
            'possible_idle_count': counts.get('POSSIBLE_IDLE', 0),
            'possible_suspicious_count': counts.get('POSSIBLE_CHEATING', 0),
            'insufficient_data_count': counts.get('INSUFFICIENT_DATA', 0),
            'normal_count': counts.get('NORMAL', 0),
            'data_quality_breakdown': dict(quality),
            'disclaimer': 'Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.',
        }

    def behavior_rows(self, *, class_id: str | None, course_id: str | None = None, classification: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        q = self.db.query(AnalyticsLearningBehaviorSnapshot)
        if class_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.class_id == class_id)
        if course_id:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.course_id == course_id)
        if classification:
            q = q.filter(AnalyticsLearningBehaviorSnapshot.classification == classification)
        total = q.count()
        rows = q.order_by(AnalyticsLearningBehaviorSnapshot.suspicious_score.desc(), AnalyticsLearningBehaviorSnapshot.calculated_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)).all()
        return {
            'total': total,
            'items': [
                {
                    'username': r.username,
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
                for r in rows
            ],
        }
