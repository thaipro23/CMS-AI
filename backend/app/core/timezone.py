from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh'
VN_TZ = ZoneInfo(VIETNAM_TIME_ZONE)


def _normalize_raw_datetime(value: str) -> str:
    raw = str(value or '').strip()
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    return raw


def to_vn_datetime(value: Any, *, assume_naive_vn: bool = True) -> datetime | None:
    """Parse/convert any datetime-like value to timezone-aware Asia/Ho_Chi_Minh.

    External systems may send UTC (`Z`), offset datetimes (`+00:00`, `+07:00`),
    or naive datetimes. Offset-aware values are converted to Vietnam time. Naive
    values are treated as Vietnam-local by default because DB columns in this
    project are stored as naive application timestamps.
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        raw = _normalize_raw_datetime(str(value))
        if not raw:
            return None
        # Accept common Vietnamese date-only/date-time strings first.
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%d-%m-%Y'):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except Exception:
                dt = None  # type: ignore[assignment]
        else:
            try:
                dt = datetime.fromisoformat(raw)
            except Exception:
                return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=VN_TZ) if assume_naive_vn else dt.replace(tzinfo=timezone.utc).astimezone(VN_TZ)
    return dt.astimezone(VN_TZ)


def to_vn_date(value: Any, *, assume_naive_vn: bool = True) -> date | None:
    dt = to_vn_datetime(value, assume_naive_vn=assume_naive_vn)
    return dt.date() if dt else None


def to_vn_naive_datetime(value: Any, *, assume_naive_vn: bool = True) -> datetime | None:
    dt = to_vn_datetime(value, assume_naive_vn=assume_naive_vn)
    return dt.replace(tzinfo=None) if dt else None


def to_vn_iso(value: Any, *, assume_naive_vn: bool = True) -> str | None:
    dt = to_vn_datetime(value, assume_naive_vn=assume_naive_vn)
    return dt.isoformat() if dt else None


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def vn_now_naive() -> datetime:
    return vn_now().replace(tzinfo=None)
