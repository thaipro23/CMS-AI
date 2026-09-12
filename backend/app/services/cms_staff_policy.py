from __future__ import annotations

from typing import Any


def cms_staff_required_for_role(role_code: str | None) -> bool:
    """Only a campus owner needs global access to Django CMS/Studio.

    Business roles remain authoritative in Dash CMS.  This flag grants the
    minimum Open edX capability required to enter CMS; it must never imply
    ``is_superuser``.
    """

    return str(role_code or '').strip().upper() == 'CAMPUS_OWNER'


def validate_cms_provisioning(match: dict[str, Any], *, require_staff: bool) -> dict[str, Any]:
    """Validate the connector's post-write account state."""

    if match.get('exists') is not True:
        raise RuntimeError('Open edX Connector chưa xác nhận tài khoản CMS đã tồn tại.')
    if match.get('user_profile_ok') is False:
        raise RuntimeError('Tài khoản CMS chưa có UserProfile hợp lệ.')
    if require_staff and match.get('is_staff') is not True:
        raise RuntimeError('Open edX Connector chưa xác nhận quyền CMS staff cho Chủ cơ sở.')
    return dict(match)
