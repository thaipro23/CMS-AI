from __future__ import annotations

from typing import Any


REPLICA = 'replica'
PRIMARY_AFTER_ENROLLMENT = 'primary_after_enrollment'


def class_analytics_read_consistency(*, immediate_after_enrollment: bool) -> str:
    return PRIMARY_AFTER_ENROLLMENT if immediate_after_enrollment else REPLICA


def validate_analytics_read_consistency(response: dict[str, Any], *, requested: str) -> None:
    """Require an explicit connector acknowledgement for every primary read."""

    if requested == PRIMARY_AFTER_ENROLLMENT and response.get('read_consistency') != PRIMARY_AFTER_ENROLLMENT:
        raise RuntimeError('Open edX Connector chưa xác nhận lần đọc primary ngay sau enrollment.')
