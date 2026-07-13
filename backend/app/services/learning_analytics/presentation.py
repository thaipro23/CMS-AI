from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any


def safe_label(classification: str | None, display_label: str | None = None) -> str:
    value = str(classification or '').upper()
    mapping = {
        'LIKELY_REAL_LEARNING': 'Có dấu hiệu học thật',
        'POSSIBLE_IDLE': 'Có khả năng treo máy',
        'POSSIBLE_ANOMALY': 'Dấu hiệu bất thường cần kiểm tra',
        'POSSIBLE_CHEATING': 'Dấu hiệu bất thường cần kiểm tra',
        'INSUFFICIENT_DATA': 'Chưa đủ dữ liệu',
        'NORMAL': 'Chưa thấy bất thường rõ',
    }
    return mapping.get(value) or display_label or 'Chưa đủ dữ liệu'


def recommended_action_label(value: str | None) -> str:
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


def parse_datetime_filter(value: Any) -> datetime | None:
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


def csv_setting_set(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        parts = value
    else:
        parts = str(value).replace(';', ',').split(',')
    return {str(part).strip().lower() for part in parts if str(part).strip()}


def sla_status(issues: list[dict[str, Any]]) -> str:
    severities = {str(item.get('severity') or '').upper() for item in issues}
    if 'BLOCKER' in severities:
        return 'BLOCKED'
    if 'WARNING' in severities:
        return 'WARNING'
    return 'OK'


def timeline_weeks_from_sessions(rows: list[Any]) -> list[dict[str, Any]]:
    by_week: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        by_week[int(row.week_index or 0)].append(row)
    result: list[dict[str, Any]] = []
    for week in sorted(k for k in by_week if k > 0):
        result.append({'week_index': week, 'sessions': [r.session_index for r in sorted(by_week[week], key=lambda item: item.session_index)]})
    return result


def empty_class_behavior_overview_summary() -> dict[str, Any]:
    return {
        'total_classes': 0,
        'total_students': 0,
        'roster_count': 0,
        'snapshot_count': 0,
        'missing_snapshot_count': 0,
        'likely_real_learning_count': 0,
        'possible_idle_count': 0,
        'possible_suspicious_count': 0,
        'insufficient_data_count': 0,
        'normal_count': 0,
        'not_calculated_class_count': 0,
        'last_activity_at': None,
        'calculated_at': None,
    }


def class_behavior_focus_count(behavior: dict[str, Any], classification: str) -> int:
    if classification == 'LIKELY_REAL_LEARNING':
        return int(behavior.get('likely_real_learning_count') or 0)
    if classification == 'POSSIBLE_IDLE':
        return int(behavior.get('possible_idle_count') or 0)
    if classification == 'POSSIBLE_ANOMALY':
        return int(behavior.get('possible_suspicious_count') or 0)
    if classification == 'INSUFFICIENT_DATA':
        return int(behavior.get('insufficient_data_count') or 0)
    if classification == 'NORMAL':
        return int(behavior.get('normal_count') or 0)
    return int(behavior.get('total_students') or 0)


def dominant_classification(behavior: dict[str, Any]) -> str:
    candidates = [
        ('POSSIBLE_ANOMALY', int(behavior.get('possible_suspicious_count') or 0)),
        ('POSSIBLE_IDLE', int(behavior.get('possible_idle_count') or 0)),
        ('INSUFFICIENT_DATA', int(behavior.get('insufficient_data_count') or 0)),
        ('LIKELY_REAL_LEARNING', int(behavior.get('likely_real_learning_count') or 0)),
        ('NORMAL', int(behavior.get('normal_count') or 0)),
    ]
    label, count = max(candidates, key=lambda item: item[1])
    return label if count > 0 else 'INSUFFICIENT_DATA'


def iso_or_none(value: Any) -> str | None:
    return value.isoformat() if value else None
