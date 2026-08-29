from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_safe_value(value: Any) -> Any:
    """Return a value that can be stored in JSON columns or Celery JSON results.

    Open edX/Django responses may contain datetime/date/time/Decimal/UUID,
    CourseKey/UsageKey, QueryDict-ish objects, sets/tuples, or model-like
    objects. PostgreSQL JSON columns and Celery's JSON serializer fail on those
    unless every nested value is normalized first.
    """
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe_value(item) for item in value]
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
    # Opaque keys, Django model-ish objects, lazy translations, etc.
    return str(value)


def json_default(value: Any) -> Any:
    return json_safe_value(value)


def json_dumps_safe(value: Any) -> str:
    return json.dumps(json_safe_value(value), ensure_ascii=False, default=json_default)
