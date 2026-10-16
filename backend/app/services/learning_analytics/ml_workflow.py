"""Bounded worker-only shadow ML. No reads/writes to official grades."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from time import monotonic

from sqlalchemy import update

from app.core.config import settings
from app.models.academic import AcademicClassStudent, AcademicStudent
from app.models.learning_analytics import (AnalyticsCourseSession, AnalyticsLearningBehaviorSnapshot,
    AnalyticsQuizAttempt, AnalyticsQuizIntegrityResult, AnalyticsQuizItemSubmission,
    AnalyticsStudentVideoProgress)
from .ml_anomaly import base_result, result_key, score_cohorts
from .ml_features import build_quiz_features, build_video_features, utc, video_identity, video_outline

log = logging.getLogger(__name__)
MAX_SOURCE_ROWS = 50000
MAX_ROSTER = 20000


def ml_enabled(class_id: str | None) -> bool:
    pilots = {s.strip() for s in settings.analytics_ml_pilot_class_ids.split(',') if s.strip()}
    return settings.analytics_ml_mode == 'shadow' and bool(class_id and class_id in pilots)


class LearningMLWorkflow:
    def __init__(self, db, *, cancelled=None):
        self.db = db
        self.cancelled = cancelled or db.info.get('analytics_ml_cancelled') or (lambda: False)

    def _reference_users(self, class_id: str, course_id: str) -> tuple[list[str], set[str]]:
        from .analytics_core_service import LearningAnalyticsCoreService
        core = LearningAnalyticsCoreService(self.db)
        classes = core._resolve_recalculate_class_ids_for_courses(course_ids={course_id}).get(course_id, set())
        if class_id not in classes:
            return [], set()
        roster = self.db.query(AcademicStudent.username, AcademicClassStudent.class_id).join(
            AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id.in_(sorted(classes)), AcademicStudent.active.is_(True),
        ).order_by(AcademicStudent.username, AcademicClassStudent.class_id).limit(MAX_ROSTER+1).all()
        if len(roster) > MAX_ROSTER:
            raise ValueError('ML_SOURCE_TOO_LARGE')
        users = sorted({str(name) for name, _ in roster if name})
        targets = {str(name) for name, cls in roster if name and cls == class_id}
        return users, targets

    def _bounded(self, query):
        rows = query.limit(MAX_SOURCE_ROWS+1).all()
        if len(rows) > MAX_SOURCE_ROWS:
            raise ValueError('ML_SOURCE_TOO_LARGE')
        return rows

    def score_behavior(self, *, class_id: str, course_id: str, target_usernames: list[str], cutoff: datetime) -> dict:
        return self._run('video', class_id, course_id, target_usernames, cutoff)

    def score_quiz(self, *, class_id: str, course_id: str, target_usernames: list[str], cutoff: datetime) -> dict:
        return self._run('quiz', class_id, course_id, target_usernames, cutoff)

    def _run(self, family, class_id, course_id, target_usernames, cutoff):
        if not ml_enabled(class_id):
            return {'status': 'disabled', 'processed': 0}
        if self.cancelled():
            return {'status': 'cancelled', 'processed': 0}
        started = monotonic()
        try:
            # Savepoint prevents an optional SQL/fit failure from poisoning the rule transaction.
            with self.db.begin_nested():
                result = self._calculate(family, class_id, course_id, target_usernames, cutoff)
            log.info('Analytics ML family=%s status=%s processed=%s elapsed_ms=%s counts=%s',
                family, result['status'], result.get('processed', 0),
                round((monotonic()-started)*1000), result.get('counts', {}))
            return result
        except Exception:
            # Log the boundary without learner identities or raw payloads.
            log.warning('Analytics ML optional workflow failed family=%s', family, exc_info=False)
            return {'status': 'error', 'processed': 0, 'reason_codes': ['ML_WORKFLOW_FAILED']}

    def _calculate(self, family, class_id, course_id, target_usernames, cutoff):
        cutoff = utc(cutoff)
        if cutoff is None:
            return {'status': 'error', 'processed': 0, 'reason_codes': ['INVALID_MEASUREMENT_TIME']}
        users, target_roster = self._reference_users(class_id, course_id)
        targets = sorted(set(target_usernames) & target_roster)
        if not targets:
            return {'status': 'outside_scope', 'processed': 0}
        builds, candidate_rows = {}, []
        if family == 'video':
            model = AnalyticsLearningBehaviorSnapshot
            outlines = self._bounded(self.db.query(AnalyticsCourseSession).filter_by(course_id=course_id, active=True))
            outline, video_ids = video_outline(outlines)
            grouped = defaultdict(list)
            for row in self._bounded(self.db.query(AnalyticsStudentVideoProgress).filter(
                    AnalyticsStudentVideoProgress.course_id == course_id,
                    AnalyticsStudentVideoProgress.username.in_(users)).order_by(AnalyticsStudentVideoProgress.id)):
                if video_identity(row.video_id) in video_ids:
                    grouped[row.username].append(row)
            for user in users:
                build = build_video_features(subject_key=user, course_id=course_id,
                    outline_fingerprint=outline, videos=grouped[user], cutoff=cutoff)
                builds[(user, '')] = build
                if build.row:
                    candidate_rows.append(build.row)
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
            cancelled=lambda: self.cancelled() or not ml_enabled(class_id))
        counts, processed = Counter(), 0
        snapshots = self._bounded(self.db.query(model).filter(
            model.class_id == class_id, model.course_id == course_id,
            model.username.in_(targets)).order_by(model.id).populate_existing().with_for_update())
        for snapshot in snapshots:
            if self.cancelled() or not ml_enabled(class_id):
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
