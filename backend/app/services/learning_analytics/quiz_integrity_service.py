from __future__ import annotations

from app.models.learning_analytics import (
    AnalyticsQuizAttempt, AnalyticsQuizIntegrityResult, AnalyticsQuizItemSubmission,
)
from app.core.config import settings
from .quiz_item_materializer import quiz_tables_ready
from .quiz_integrity_rules import evaluate_quiz_integrity


def recalculate_class_integrity(db, *, class_id: str, course_id: str, usernames: list[str]):
    if not usernames or not quiz_tables_ready(db):
        return {'status': 'migration_required'}
    items = db.query(AnalyticsQuizItemSubmission).filter(
        AnalyticsQuizItemSubmission.course_id == course_id,
        AnalyticsQuizItemSubmission.username.in_(usernames),
    ).order_by(AnalyticsQuizItemSubmission.submitted_at, AnalyticsQuizItemSubmission.id).all()
    attempts = db.query(AnalyticsQuizAttempt).filter(
        AnalyticsQuizAttempt.course_id == course_id,
        AnalyticsQuizAttempt.username.in_(usernames),
    ).all()
    existing = db.query(AnalyticsQuizIntegrityResult).filter_by(class_id=class_id, course_id=course_id).all()
    previous = next((r.evidence_json for r in existing if (r.evidence_json or {}).get('partial')), {}) or {}
    results = evaluate_quiz_integrity([
        {key: getattr(item, key) for key in (
            'username', 'unit_usage_key', 'problem_usage_key', 'input_slot', 'variant',
            'content_version', 'question_hash', 'response_type', 'answer_json', 'correct',
            'submitted_at', 'reveal_requested_before',
        )} for item in items
    ], [{'username': row.username, 'unit_usage_key': row.unit_usage_key,
         **(row.evidence_json or {})} for row in attempts], {
        'cursor': previous.get('cursor', 0), 'fingerprint': previous.get('fingerprint'),
        'previous_pairs': {(r.username, r.unit_usage_key): (r.evidence_json or {}).get('pairs', [])
                           for r in existing},
        'reset_policies': settings.analytics_quiz_reset_policies,
    })
    by_key = {(r.username, r.unit_usage_key): r for r in existing}
    from datetime import datetime
    for result in results:
        key = (result['username'], result['unit_usage_key'])
        row = by_key.get(key)
        if row is None:
            row = AnalyticsQuizIntegrityResult(class_id=class_id, course_id=course_id,
                                               username=key[0], unit_usage_key=key[1])
            db.add(row)
        row.status = result['status']
        row.rule_version = result['rule_version']
        row.evidence_json = result['evidence']
        row.calculated_at = datetime.utcnow()
    db.flush()
    return {'status': 'partial' if any(r['evidence']['partial'] for r in results) else 'completed',
            'results': len(results)}
