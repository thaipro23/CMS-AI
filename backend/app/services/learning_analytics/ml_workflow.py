"""Bounded worker-only shadow ML. No reads/writes to official grades."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from time import monotonic

from sqlalchemy import update

from app.core.config import settings
from app.models.academic import AcademicClassStudent, AcademicStudent
from app.models.learning_analytics import (AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
    AnalyticsQuizAttempt, AnalyticsQuizIntegrityResult, AnalyticsQuizItemSubmission,
    AnalyticsStudentVideoProgress)
from .ml_anomaly import base_result, result_key, score_cohorts
from .ml_features import build_quiz_features, build_video_features, fingerprint, utc, video_identity, video_outline

log = logging.getLogger(__name__)
MAX_SOURCE_ROWS = 50000
MAX_ROSTER = 20000


class _MLCancelled(Exception):
    """Roll back the optional savepoint when a job is disabled or cancelled."""


def ml_enabled(class_id: str | None, family: str = 'video') -> bool:
    pilots = {s.strip() for s in settings.analytics_ml_pilot_class_ids.split(',') if s.strip()}
    enabled = settings.analytics_ml_video_enabled if family == 'video' else settings.analytics_ml_quiz_enabled if family == 'quiz' else False
    return settings.analytics_ml_mode == 'shadow' and enabled and bool(class_id and class_id in pilots)


def video_reference_courses(course_id: str | None) -> list[str]:
    courses = {s.strip() for s in settings.analytics_ml_video_reference_course_ids.split(',') if s.strip()}
    if course_id:
        courses.add(course_id)
    if len(courses) > 20:
        raise ValueError('ML_SOURCE_TOO_LARGE')
    return sorted(courses)


def video_reference_scope(course_id: str | None) -> str:
    return fingerprint(video_reference_courses(course_id))


class LearningMLWorkflow:
    def __init__(self, db, *, cancelled=None):
        self.db = db
        self.cancelled = cancelled or db.info.get('analytics_ml_cancelled') or (lambda: False)
        self._checkpoint = lambda: None

    def _reference_users(self, class_id: str, course_id: str) -> tuple[list[str], set[str]]:
        from .analytics_core_service import LearningAnalyticsCoreService
        core = LearningAnalyticsCoreService(self.db)
        classes = core._resolve_recalculate_class_ids_for_courses(course_ids={course_id}).get(course_id, set())
        self._checkpoint()
        if class_id not in classes:
            return [], set()
        roster = self.db.query(AcademicStudent.username, AcademicClassStudent.class_id).join(
            AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id.in_(sorted(classes)), AcademicStudent.active.is_(True),
        ).order_by(AcademicStudent.username, AcademicClassStudent.class_id).limit(MAX_ROSTER+1).all()
        self._checkpoint()
        if len(roster) > MAX_ROSTER:
            raise ValueError('ML_SOURCE_TOO_LARGE')
        users = sorted({str(name) for name, _ in roster if name})
        targets = {str(name) for name, cls in roster if name and cls == class_id}
        return users, targets

    def _bounded(self, query):
        self._checkpoint()
        rows = query.limit(MAX_SOURCE_ROWS+1).all()
        self._checkpoint()
        if len(rows) > MAX_SOURCE_ROWS:
            raise ValueError('ML_SOURCE_TOO_LARGE')
        return rows

    def score_behavior(self, *, class_id: str, course_id: str, target_usernames: list[str], cutoff: datetime) -> dict:
        return self._run('video', class_id, course_id, target_usernames, cutoff)

    def score_quiz(self, *, class_id: str, course_id: str, target_usernames: list[str], cutoff: datetime) -> dict:
        return self._run('quiz', class_id, course_id, target_usernames, cutoff)

    def _run(self, family, class_id, course_id, target_usernames, cutoff):
        if not ml_enabled(class_id, family):
            return {'status': 'disabled', 'processed': 0}
        if self.cancelled():
            return {'status': 'cancelled', 'processed': 0}
        def checkpoint():
            if self.cancelled() or not ml_enabled(class_id, family):
                raise _MLCancelled()
        self._checkpoint = checkpoint
        started = monotonic()
        try:
            # Savepoint prevents an optional SQL/fit failure from poisoning the rule transaction.
            with self.db.begin_nested():
                result = self._calculate(family, class_id, course_id, target_usernames, cutoff)
            log.info('Analytics ML family=%s status=%s processed=%s elapsed_ms=%s counts=%s',
                family, result['status'], result.get('processed', 0),
                round((monotonic()-started)*1000), result.get('counts', {}))
            return result
        except _MLCancelled:
            return {'status': 'cancelled', 'processed': 0}
        except Exception:
            # Log the boundary without learner identities or raw payloads.
            log.warning('Analytics ML optional workflow failed family=%s', family, exc_info=False)
            return {'status': 'error', 'processed': 0, 'reason_codes': ['ML_WORKFLOW_FAILED']}

    def _calculate(self, family, class_id, course_id, target_usernames, cutoff):
        cutoff = utc(cutoff)
        if cutoff is None:
            return {'status': 'error', 'processed': 0, 'reason_codes': ['INVALID_MEASUREMENT_TIME']}
        reference_scope = video_reference_scope(course_id) if family == 'video' else None
        if family == 'video':
            target_roster, builds, candidate_rows = self._video_builds(class_id, course_id, cutoff)
        else:
            users, target_roster = self._reference_users(class_id, course_id)
            builds, candidate_rows = {}, []
        targets = sorted(set(target_usernames) & target_roster)
        if not targets:
            return {'status': 'outside_scope', 'processed': 0}
        if family == 'video':
            model = AnalyticsLearningBehaviorSnapshot
        else:
            model = AnalyticsQuizIntegrityResult
            attempts = self._bounded(self.db.query(AnalyticsQuizAttempt).filter(
                AnalyticsQuizAttempt.course_id == course_id, AnalyticsQuizAttempt.username.in_(users),
            ).order_by(AnalyticsQuizAttempt.started_at, AnalyticsQuizAttempt.attempt_no, AnalyticsQuizAttempt.id))
            items_by_attempt = defaultdict(list)
            for item in self._bounded(self.db.query(AnalyticsQuizItemSubmission).filter(
                    AnalyticsQuizItemSubmission.course_id == course_id,
                    AnalyticsQuizItemSubmission.username.in_(users)).order_by(AnalyticsQuizItemSubmission.submitted_at, AnalyticsQuizItemSubmission.id)):
                items_by_attempt[item.attempt_id].append(item)
            from .analytics_core_service import LearningAnalyticsCoreService
            aliases = LearningAnalyticsCoreService(self.db)._quiz_unit_aliases(course_id)
            first_eligible = {}
            for attempt in attempts:
                self._checkpoint()
                unit = aliases.get(attempt.unit_usage_key, attempt.unit_usage_key)
                key = (attempt.username, unit)
                build = build_quiz_features(subject_key=attempt.username, course_id=course_id,
                    unit_usage_key=unit, attempt=attempt, items=items_by_attempt[attempt.id], cutoff=cutoff)
                builds.setdefault(key, build)
                if build.row:
                    # One reference per learner/content cohort, regardless of retries.
                    cohort_key = (*key, build.row.cohort_key)
                    if cohort_key not in first_eligible:
                        first_eligible[cohort_key] = build
                        candidate_rows.append(build.row)
                    # Latest observed cohort for the one latest-evidence slot.
                    builds[key] = first_eligible[cohort_key]
        scores = score_cohorts(candidate_rows,
            min_students=settings.analytics_ml_min_reference_students,
            max_students=settings.analytics_ml_max_reference_students,
            cancelled=lambda: self.cancelled() or not ml_enabled(class_id, family))
        if (self.cancelled() or not ml_enabled(class_id, family)
                or (family == 'video' and reference_scope != video_reference_scope(course_id))):
            return {'status': 'cancelled', 'processed': 0}
        counts, processed = Counter(), 0
        snapshots = self._bounded(self.db.query(model).filter(
            model.class_id == class_id, model.course_id == course_id,
            model.username.in_(targets)).order_by(model.id).populate_existing().with_for_update())
        for snapshot in snapshots:
            if self.cancelled() or not ml_enabled(class_id, family):
                return {'status': 'cancelled', 'processed': processed, 'counts': dict(counts)}
            stamp = utc(snapshot.calculated_at)
            if stamp is None or stamp > cutoff:
                continue
            unit = snapshot.unit_usage_key if family == 'quiz' else ''
            build = builds.get((snapshot.username, unit))
            if build and build.row:
                analysis = scores[result_key(build.row)]
            else:
                analysis = base_result(None, family=family,
                    reasons=list(build.reasons) if build else ['NO_MEASURED_ACTIVITY'])
            analysis = {**analysis, 'class_id': class_id, 'course_id': course_id,
                'unit_usage_key': unit or None, 'cutoff': cutoff.isoformat(),
                'calculated_at': cutoff.isoformat(), 'snapshot_calculated_at': stamp.isoformat()}
            if family == 'video':
                analysis['reference_scope'] = reference_scope
            old = snapshot.evidence_json or {}
            previous_cutoff = utc((old.get('ml') or {}).get('cutoff'))
            if previous_cutoff and previous_cutoff > cutoff:
                continue
            changed = self.db.execute(update(model).where(
                model.id == snapshot.id, model.calculated_at == snapshot.calculated_at,
            ).values(evidence_json={**old, 'ml': analysis}), execution_options={'synchronize_session': False})
            if changed.rowcount:
                self.db.expire(snapshot, ['evidence_json'])
                counts[analysis['status']] += 1
                processed += 1
        return {'status': 'error' if counts['ERROR'] else 'completed', 'processed': processed,
                'counts': dict(counts)}

    def _video_builds(self, class_id, course_id, cutoff):
        from .analytics_core_service import LearningAnalyticsCoreService
        courses = video_reference_courses(course_id)
        scope = fingerprint(courses)
        mapped = LearningAnalyticsCoreService(self.db)._resolve_recalculate_class_ids_for_courses(course_ids=set(courses))
        self._checkpoint()
        if class_id not in mapped.get(course_id, set()):
            return set(), {}, []
        classes = sorted(set().union(*mapped.values()))
        roster = self.db.query(AcademicStudent.username, AcademicClassStudent.class_id).join(
            AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id.in_(classes), AcademicStudent.active.is_(True),
        ).order_by(AcademicStudent.username, AcademicClassStudent.class_id).limit(MAX_ROSTER+1).all()
        self._checkpoint()
        if len(roster) > MAX_ROSTER:
            raise ValueError('ML_SOURCE_TOO_LARGE')
        course_users = {c: {str(u) for u, cls in roster if u and cls in mapped.get(c,set())} for c in courses}
        users = sorted(set().union(*course_users.values()))
        targets = {str(u) for u, cls in roster if u and cls == class_id}
        outlines = defaultdict(list)
        for row in self._bounded(self.db.query(AnalyticsCourseSession).filter(
                AnalyticsCourseSession.course_id.in_(courses), AnalyticsCourseSession.active.is_(True))):
            outlines[row.course_id].append(row)
        identities = {c: video_outline(outlines[c]) for c in courses}
        grouped = defaultdict(list)
        fields = ('duration_seconds','session_index','completion_percent','estimated_watch_seconds',
            'passive_watch_seconds','seek_count','last_event_at','evidence_json')
        for index, row in enumerate(self._bounded(self.db.query(AnalyticsStudentVideoProgress).filter(
                AnalyticsStudentVideoProgress.course_id.in_(courses),
                AnalyticsStudentVideoProgress.username.in_(users)).order_by(AnalyticsStudentVideoProgress.id))):
            if index % 256 == 0:
                self._checkpoint()
            if (row.username in course_users.get(row.course_id,set())
                    and video_identity(row.video_id) in identities[row.course_id][1]):
                grouped[row.username].append({**{key:getattr(row,key) for key in fields},
                    'video_id':fingerprint([row.course_id,video_identity(row.video_id)])})
        outline = fingerprint({c: v[0] for c,v in identities.items()}) if any(v[0] for v in identities.values()) else ''
        builds, candidates = {}, []
        for user in users:
            self._checkpoint()
            build = build_video_features(subject_key=user, course_id=course_id,
                outline_fingerprint=outline, videos=grouped[user], cutoff=cutoff, reference_scope=scope)
            if build.row:
                build = replace(build, row=replace(build.row, metadata={**build.row.metadata,
                    'pooled_course_count':sum(bool(course_users[c]) and bool(identities[c][1]) for c in courses)}))
                candidates.append(build.row)
            builds[(user,'')] = build
        return targets, builds, candidates
