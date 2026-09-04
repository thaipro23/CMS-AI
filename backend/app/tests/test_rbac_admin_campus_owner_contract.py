from types import SimpleNamespace

from app.models.rbac import RBACPermission
from app.services.business_rbac import (
    BusinessRBACService,
    CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS,
    _is_all_campus_assignment,
)


def assignment(scope_type: str, scope_id: str, role_code: str = 'CAMPUS_OWNER'):
    return SimpleNamespace(role_code=role_code, scope_type=scope_type, scope_id=scope_id)


def test_only_all_campus_owner_gets_small_campus_operations_bundle():
    assert _is_all_campus_assignment(assignment('CAMPUS', '*')) is True
    assert _is_all_campus_assignment(assignment('SYSTEM', '*')) is True
    assert _is_all_campus_assignment(assignment('CAMPUS', 'HN')) is False
    assert 'department.manage_all' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'rbac.view' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'user.manage_all' not in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS


class _Query:
    def all(self):
        return [SimpleNamespace(code='future.permission')]


class _Db:
    def query(self, model):
        assert model is RBACPermission
        return _Query()


def test_system_admin_effective_permissions_include_future_catalog_permissions(monkeypatch):
    service = BusinessRBACService(_Db())
    monkeypatch.setattr(service, 'is_system_admin', lambda user: True)
    monkeypatch.setattr(service, 'active_assignments_for_actor', lambda user: [])
    monkeypatch.setattr(service, '_has_ap_teacher_assignment', lambda user: False)
    permissions = service.effective_permissions_for_user(SimpleNamespace())
    assert 'future.permission' in permissions
    assert 'rbac.view' in permissions
