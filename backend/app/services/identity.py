from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.core.timezone import vn_now_naive


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def normalize_email_identity(email: str) -> dict[str, str]:
    normalized = str(email or '').strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError('Email phân quyền không hợp lệ.')
    username = normalized.split('@', 1)[0].strip()
    if not username:
        raise ValueError('Email phải có phần username trước ký tự @.')
    return {'email': normalized[:254], 'username': username[:255]}


def upsert_login(
    db: 'Session',
    *,
    user_id: str,
    email: str | None = None,
    username: str | None = None,
    display_name: str | None = None,
    logged_at: datetime | None = None,
) -> AIUserProfile:
    from app.models.identity import AIUserProfile
    key = str(user_id or '').strip()
    if not key:
        raise ValueError('Thiếu user_id khi ghi nhận đăng nhập.')
    row = db.get(AIUserProfile, key)
    if row is None:
        row = AIUserProfile(user_id=key)
    row.email = str(email or row.email or '').strip().lower() or None
    row.username = str(username or row.username or key).strip() or key
    row.display_name = str(display_name or row.display_name or '').strip() or None
    row.last_login_at = logged_at or vn_now_naive()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def login_by_user_ids(db: 'Session', user_ids: list[str]) -> dict[str, Any]:
    from app.models.identity import AIUserProfile
    keys = sorted({str(item).strip() for item in user_ids if str(item or '').strip()})
    if not keys:
        return {}
    try:
        rows = db.query(AIUserProfile).filter(AIUserProfile.user_id.in_(keys)).all()
    except Exception:
        # Safe during rolling deploys and legacy SQLite fixtures before migration.
        db.rollback()
        return {}
    return {row.user_id: row for row in rows}
