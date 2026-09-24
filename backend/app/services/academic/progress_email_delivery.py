from __future__ import annotations

import hashlib
import hmac
from typing import Any, Literal

from app.core.config import settings
from app.core.privacy import normalize_email


DeliveryAction = Literal['create_idempotently', 'poll', 'done']


def _hmac_hex(purpose: str, value: str) -> str:
    secret = str(settings.jwt_secret or '').encode('utf-8')
    payload = f'{purpose}\0{value}'.encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def build_delivery_intent(*, job_id: str, recipient: dict[str, Any]) -> dict[str, Any]:
    """Build the durable, public-safe intent persisted before provider I/O.

    The actual address remains in the academic student row.  The HMAC freezes
    that address for this job without putting it in job JSON or logs; a retry
    may only use the address when it still matches the frozen fingerprint.
    """
    student_id = str(recipient.get('student_id') or '').strip()
    email = normalize_email(recipient.get('private_email'))
    clean_job_id = str(job_id or '').strip()
    if not clean_job_id or not student_id or not email:
        raise ValueError('invalid_progress_email_delivery_intent')
    intent_identity = f'{clean_job_id}\0{student_id}'
    provider_key = f'progress-email:v1:{_hmac_hex("provider-key", intent_identity)}'
    return {
        'student_id': student_id,
        'idempotency_key': provider_key,
        'recipient_fingerprint': _hmac_hex(
            'recipient-via-provider-key',
            f'{provider_key}\0{student_id}\0{email}',
        ),
        'provider_state': 'intent_created',
        'status': 'INTENT_CREATED',
    }


def recipient_matches_intent(intent: dict[str, Any], email: Any) -> bool:
    normalized = normalize_email(email)
    student_id = str(intent.get('student_id') or '').strip()
    provider_key = str(intent.get('idempotency_key') or '').strip()
    expected = str(intent.get('recipient_fingerprint') or '').strip()
    if not normalized or not student_id or not provider_key or not expected:
        return False
    candidate = _hmac_hex('recipient-via-provider-key', f'{provider_key}\0{student_id}\0{normalized}')
    return hmac.compare_digest(expected, candidate)


def delivery_reconciliation_action(intent: dict[str, Any]) -> DeliveryAction:
    state = str(intent.get('provider_state') or '').strip().lower()
    if state in {'intent_created', 'provider_unknown'}:
        return 'create_idempotently'
    if state == 'provider_created' and str(intent.get('session_id') or '').strip():
        return 'poll'
    if state == 'terminal':
        return 'done'
    raise ValueError('invalid_progress_email_provider_state')
