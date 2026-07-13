from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.rbac import UserContext
from app.models.academic import AcademicTerm
from app.services.openedx_student_insight import mask_email

def _actor_names(user: UserContext) -> set[str]:
    raw = user.raw_claims or {}
    values = {
        user.user_id,
        user.username,
        user.email,
        raw.get('username'),
        raw.get('preferred_username'),
        raw.get('email'),
    }
    return {str(item).strip().lower() for item in values if str(item or '').strip()}


def _page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 50)))
    return page, page_size


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {'1', 'true', 'yes', 'y', 'active'}:
        return True
    if raw in {'0', 'false', 'no', 'n', 'inactive'}:
        return False
    return bool(raw)




def _clean_token(value: Any) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '', str(value or '')).upper()


def _normalize_text_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _natural_sort_key(value: Any) -> list[Any]:
    raw = str(value or '').strip().lower()
    parts = re.split(r'(\d+)', raw)
    return [int(part) if part.isdigit() else part for part in parts]


def _parse_openedx_course_id(course_id: str) -> dict[str, str] | None:
    raw = str(course_id or '').strip()
    match = re.match(r'^course-v1:([^+\s]+)\+([^+\s]+)\+([^+\s]+)$', raw)
    if not match:
        return None
    return {'org': match.group(1), 'course': match.group(2), 'run': match.group(3), 'raw': raw}


def _term_run_candidates(term: AcademicTerm | None) -> set[str]:
    if not term:
        return set()
    raw_values = {term.term_code, term.term_name}
    candidates: set[str] = set()
    for raw in raw_values:
        text = str(raw or '').strip()
        if not text:
            continue
        candidates.add(_clean_token(text))
        lower = text.lower()
        year_match = re.search(r'(20\d{2}|\d{2})', lower)
        year = year_match.group(1) if year_match else ''
        yy = year[-2:] if year else ''
        yyyy = f'20{yy}' if len(year) == 2 else year
        prefix = ''
        if any(key in lower for key in ['spring', 'sp', 'xuân']):
            prefix = 'SP'
        elif any(key in lower for key in ['summer', 'su', 'hè']):
            prefix = 'SU'
        elif any(key in lower for key in ['fall', 'fa', 'autumn', 'thu']):
            prefix = 'FA'
        if prefix and yy:
            candidates.add(f'{prefix}{yy}')
            candidates.add(f'{prefix}{yyyy}')
    return {item for item in candidates if item}


def _suggest_course_run(term: AcademicTerm | None) -> str:
    candidates = sorted(_term_run_candidates(term), key=lambda item: (len(item), item))
    for item in candidates:
        if re.match(r'^(SP|SU|FA)\d{2,4}$', item):
            return item
    return candidates[0] if candidates else 'TERM'


def _check(code: str, status_value: str, message: str, metadata: dict[str, Any] | None = None, *, blocking: bool | None = None) -> dict[str, Any]:
    if blocking is None:
        blocking = status_value == 'fail'
    return {'code': code, 'status': status_value, 'message': message, 'metadata': metadata or {}, 'blocking': bool(blocking)}


def _validation_result(checks: list[dict[str, Any]], *, suggested: str | None = None, parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    has_fail = any(item.get('status') == 'fail' for item in checks)
    has_warn = any(item.get('status') == 'warn' for item in checks)
    risk = 'high' if has_fail else ('medium' if has_warn else 'low')
    if has_fail:
        message = 'Mapping chưa an toàn. Cần sửa lỗi trước khi lưu.'
    elif has_warn:
        message = 'Mapping có cảnh báo. Có thể lưu nếu đã kiểm tra thủ công.'
    else:
        message = 'Mapping hợp lệ.'
    return {
        'ok': not has_fail,
        'can_save': not has_fail,
        'risk_level': risk,
        'message': message,
        'checks': checks,
        'suggested_openedx_course_id': suggested,
        'parsed_course': parsed,
    }

def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_mapping_raw(result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    safe: dict[str, Any] = {}
    for key, value in result.items():
        if key in {'email', 'openedx_email', 'ap_email'}:
            safe[key] = mask_email(value)
        elif key in {'full_name', 'name', 'phone'}:
            safe[key] = '***REDACTED***'
        else:
            safe[key] = _json_safe_value(value)
    return safe


def _derive_mapping_status(result: dict[str, Any] | None) -> tuple[str, str, float, str]:
    result = result or {}
    explicit_status = str(result.get('match_status') or '').strip().lower()
    explicit_method = str(result.get('match_method') or '').strip().lower()
    exists = result.get('exists')
    is_active = result.get('is_active')
    note = str(result.get('note') or result.get('message') or '').strip()
    if explicit_status:
        status = explicit_status
    elif exists is False:
        status = 'missing'
    elif result.get('ambiguous'):
        status = 'ambiguous'
    elif exists is True and is_active is False:
        status = 'inactive'
    elif exists is True:
        status = 'matched'
    else:
        status = 'manual_required'
    if explicit_method:
        method = explicit_method
    elif status in {'matched', 'inactive'}:
        method = 'exact_ap_username'
    elif status == 'missing':
        method = 'not_found'
    elif status == 'ambiguous':
        method = 'ambiguous'
    else:
        method = 'manual_required'
    confidence = 1.0 if status == 'matched' and method == 'exact_ap_username' else 0.0
    if status == 'inactive':
        confidence = 0.9
    if status == 'ambiguous':
        confidence = 0.5
    return status, method, confidence, note


@dataclass(frozen=True)
class AccessDecision:
    unrestricted: bool
    teacher_ids: set[str]
    subject_codes: set[str]
    campus_codes: set[str]
