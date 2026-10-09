from __future__ import annotations

from datetime import datetime
from .quiz_attempt_analyzer import SERVER_SESSION_PROVENANCE


def serialize_quiz_attempt(row, title: str) -> dict:
    evidence = row.evidence_json or {}
    trusted = evidence.get('session_event_provenance') == SERVER_SESSION_PROVENANCE
    start = None
    try:
        if trusted and evidence.get('start_request_at'):
            start = datetime.fromisoformat(evidence['start_request_at'])
    except (ValueError, TypeError):
        pass
    last = row.last_submission_at
    valid = bool(start and last and last >= start)
    return {
        'id': row.id, 'unit_usage_key': row.unit_usage_key, 'quiz_title': title,
        'attempt_no': row.attempt_no,
        'started_at': start.isoformat() if start else None,
        'first_submission_at': row.first_submission_at.isoformat() if row.first_submission_at else None,
        'last_submission_at': last.isoformat() if last else None,
        'duration_seconds': (last - start).total_seconds() if valid else None,
        'duration_source': 'START_REQUEST_TO_LAST_SUBMISSION' if valid else 'UNKNOWN',
        'submission_count': row.submission_count,
        'score_earned': row.score_earned, 'score_possible': row.score_possible,
        'reset_request_count': row.reset_count if trusted else 0, 'answer_reveal_request_count': row.showanswer_count,
        'rapid_submission_burst': bool(evidence.get('rapid_submission_burst')),
        'median_submission_gap_seconds': evidence.get('median_submission_gap_seconds'),
    }


def visible_pair_evidence(evidence: dict, allowed_names: set[str]) -> dict:
    return {**evidence, 'pairs': [p for p in evidence.get('pairs', [])
                                if p.get('other_username') in allowed_names]}


def read_quiz_detail(parent, *, class_id: str, course_id: str, username: str) -> dict:
    from app.models.learning_analytics import AnalyticsQuizAttempt, AnalyticsQuizIntegrityResult, AnalyticsCourseSession
    from .quiz_item_materializer import quiz_tables_ready
    if not class_id or not course_id:
        return {'attempts': [], 'results': [], 'status': 'MISSING_SCOPE', 'has_more': False}
    roster = parent._class_student_usernames(class_id)
    if username not in roster:
        return {'attempts': [], 'results': [], 'status': 'OUTSIDE_CLASS', 'has_more': False}
    db = parent.db
    attempts = db.query(AnalyticsQuizAttempt).filter_by(course_id=course_id, username=username).order_by(
        AnalyticsQuizAttempt.last_submission_at.desc().nullslast(), AnalyticsQuizAttempt.attempt_no.desc(),
        AnalyticsQuizAttempt.id,
    ).limit(201).all()
    more = len(attempts) > 200
    attempts = attempts[:200]
    mappings = db.query(AnalyticsCourseSession).filter_by(course_id=course_id, active=True).all()
    def title(row):
        matches = [m for m in mappings if parent._key_match(row.unit_usage_key, m.quiz_usage_key)
                   or parent._key_match(row.sequence_usage_key, m.session_key)]
        return f'{matches[0].session_title} · Quiz' if len(matches) == 1 else f'Quiz · {row.unit_usage_key.rsplit("@", 1)[-1][:16]}'
    results = []
    ready = quiz_tables_ready(db)
    if ready:
        stored = db.query(AnalyticsQuizIntegrityResult).filter_by(
            class_id=class_id, course_id=course_id, username=username,
        ).all()
        results = [{'unit_usage_key': row.unit_usage_key, 'status': row.status,
                    'rule_version': row.rule_version, 'evidence': visible_pair_evidence(row.evidence_json or {}, roster),
                    'calculated_at': row.calculated_at.isoformat()} for row in stored]
    return {'attempts': [serialize_quiz_attempt(row, title(row)) for row in attempts],
            'results': results, 'status': 'READY' if ready else 'MIGRATION_REQUIRED', 'has_more': more}
