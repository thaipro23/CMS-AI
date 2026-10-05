from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from sqlalchemy import inspect

from app.models.learning_analytics import AnalyticsQuizItemReceipt, AnalyticsQuizItemSubmission
from .quiz_attempt_analyzer import QuizAttemptFeature


def quiz_tables_ready(db) -> bool:
    inspector = inspect(db.get_bind())
    return all(inspector.has_table(name) for name in (
        'analytics_quiz_item_submissions', 'analytics_quiz_item_receipts',
        'analytics_quiz_integrity_results',
    ))


def materialize_quiz_items(db, feature: QuizAttemptFeature, *, attempt_id: str) -> dict[str, int]:
    inserted = skipped = 0
    # SessionLocal disables autoflush: queries cannot see rows queued earlier
    # in this feature. Track them explicitly instead of inserting duplicates.
    items_by_key = {}
    # Late requests still invalidate retained answers after their raw checks expire.
    for request in feature.answer_reveal_requests:
        db.query(AnalyticsQuizItemSubmission).filter(
            AnalyticsQuizItemSubmission.course_id == feature.course_id,
            AnalyticsQuizItemSubmission.username == feature.username,
            AnalyticsQuizItemSubmission.unit_usage_key == feature.unit_usage_key,
            AnalyticsQuizItemSubmission.problem_usage_key == request['problem_usage_key'],
            AnalyticsQuizItemSubmission.submitted_at >= datetime.fromisoformat(request['requested_at']),
        ).update({'reveal_requested_before': True}, synchronize_session='fetch')
    for event in feature.raw_submissions:
        if event['event_type'] != 'problem_check' or event['event_source'] != 'server':
            if event['event_type'] == 'problem_check' and event.get('event_id'):
                if not db.get(AnalyticsQuizItemReceipt, event['event_id']):
                    db.add(AnalyticsQuizItemReceipt(event_id=event['event_id']))
                skipped += 1
            continue
        payload = event['payload']
        detail = payload.get('submission') or {}
        answers = payload.get('answers') or {}
        correct_map = payload.get('correct_map') or {}
        if not all(isinstance(v, dict) for v in (detail, answers, correct_map)):
            skipped += 1
            continue
        fingerprint = hashlib.sha256(json.dumps({
            'course': feature.course_id, 'user': feature.username,
            'problem': event['problem_usage_key'], 'time': event['submitted_at'].isoformat(),
            'payload': payload,
        }, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        module = event.get('context', {}).get('module') or {}
        module = module if isinstance(module, dict) else {}
        version = module.get('original_usage_version') or payload.get('content_version')
        reveal = any(r['problem_usage_key'] == event['problem_usage_key']
                     and datetime.fromisoformat(r['requested_at']) <= event['submitted_at']
                     for r in feature.answer_reveal_requests)
        for input_id in set(detail) | set(answers):
            data = detail.get(input_id) or {}
            data = data if isinstance(data, dict) else {}
            answer = data.get('answer', answers.get(input_id))
            response_type = str(data.get('response_type') or '')
            # Checkbox answers are sets; strings remain case-sensitive.
            if isinstance(answer, list) and response_type in {'choiceresponse', 'multiplechoiceresponse'}:
                answer = sorted(answer, key=lambda v: json.dumps(v, sort_keys=True))
            correctness = data.get('correct')
            if type(correctness) is not bool:
                entry = correct_map.get(input_id) or {}
                value = entry.get('correctness') if isinstance(entry, dict) else None
                correctness = {'correct': True, 'incorrect': False}.get(value)
            item_key = (fingerprint, str(input_id))
            existing = items_by_key.get(item_key)
            if existing is None:
                existing = db.query(AnalyticsQuizItemSubmission).filter_by(
                    event_fingerprint=fingerprint, input_id=str(input_id),
                ).first()
            if existing:
                # Same raw action can be reparsed after a late start event.
                existing.attempt_id = attempt_id
                existing.reveal_requested_before = existing.reveal_requested_before or reveal
                items_by_key[item_key] = existing
                continue
            index = payload.get('attempts')
            index = index if isinstance(index, int) and not isinstance(index, bool) else None
            # edX input IDs often embed user-local block IDs; use the suffix
            # as the response slot only within the exact same problem key.
            suffix = re.search(r'(_\d+_\d+)$', str(input_id))
            slot = suffix.group(1) if suffix else str(input_id)
            if len(slot) > 128:
                slot = 'sha256:' + hashlib.sha256(slot.encode()).hexdigest()
            row = AnalyticsQuizItemSubmission(
                event_fingerprint=fingerprint, attempt_id=attempt_id,
                course_id=feature.course_id, username=feature.username,
                unit_usage_key=feature.unit_usage_key, problem_usage_key=event['problem_usage_key'],
                input_id=str(input_id), input_slot=slot,
                variant=str(data.get('variant') or ''),
                content_version=str(version) if version is not None else None,
                question_hash=hashlib.sha256(str(data.get('question') or '').encode()).hexdigest(),
                answer_json=answer, correct=correctness, response_type=response_type,
                attempt_index=index, submitted_at=event['submitted_at'],
                reveal_requested_before=reveal,
            )
            db.add(row)
            items_by_key[item_key] = row
            inserted += 1
        if event.get('event_id') and not db.get(AnalyticsQuizItemReceipt, event['event_id']):
            # A valid server check with no metadata is explicitly processed;
            # it yields insufficient data rather than fabricated answers.
            db.add(AnalyticsQuizItemReceipt(event_id=event['event_id']))
    db.flush()
    return {'inserted': inserted, 'skipped': skipped}
