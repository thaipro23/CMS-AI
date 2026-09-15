from __future__ import annotations

import re
from typing import Any

_EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def normalize_email(value: Any) -> str | None:
    email = str(value or '').strip().lower()
    return email if email and _EMAIL_PATTERN.fullmatch(email) else None


def mask_email(value: Any) -> str | None:
    """Return an idempotent display-safe email value."""
    email = normalize_email(value)
    if not email:
        return None
    local, domain = email.rsplit('@', 1)
    if '***' in local:
        return email
    masked_local = f'{local[:1]}***' if len(local) <= 1 else f'{local[:1]}***{local[-1:]}'
    return f'{masked_local}@{domain}'
