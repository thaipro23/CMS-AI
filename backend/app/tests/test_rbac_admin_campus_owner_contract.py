from types import SimpleNamespace
from datetime import datetime
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.academic import router as academic_router, _require_academic_catalog_admin
from app.api.routes.rbac import list_assignments
from app.core.config import settings
from app.core.rbac import get_user_context, ensure_course_access, require_permission
from app.core.security import Principal, get_principal
from app.core import security
from app.db.session import Base, get_db
from app.models import cost, job  # noqa: F401
from app.models.academic import AcademicCampus
from app.models.rbac import UserRoleAssignment

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
    assert 'academic.catalog.manage' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'campus_owner.assign' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'rbac.view' in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'user.manage_all' not in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS
    assert 'department.manage_all' not in CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS


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


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(settings, 'app_env', 'production')
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        BusinessRBACService(session).ensure_default_catalog()
        session.add(AcademicCampus(campus_code='hn', campus_name='Hà Nội', branch='poly'))
        session.commit()
        yield session
    engine.dispose()


def grant(db, role='CAMPUS_OWNER', scope_type='CAMPUS', scope_id='*', user_id='owner'):
    item = UserRoleAssignment(user_id=user_id, role_code=role, scope_type=scope_type, scope_id=scope_id)
    db.add(item)
    db.commit()
    return item


def actor(db, user_id='owner'):
    return get_user_context(Principal(user_id=user_id, role='viewer', raw_claims={'username': user_id}), db)


def test_database_admin_grant_and_revocation_apply_to_existing_viewer_session(db):
    principal = Principal(user_id='sso-123', email='admin@example.test', role='viewer', course_ids=['course-a'])
    item = grant(db, role='SYSTEM_ADMIN', scope_type='SYSTEM', user_id='admin@example.test')
    user = get_user_context(principal, db)
    assert user.role == 'admin'
    ensure_course_access(user, 'course-b')
    assert require_permission('future.permission')(user, db) is user
    assert _require_academic_catalog_admin(user, db) is user
    item.revoked_at = datetime.utcnow()
    db.commit()
    user = get_user_context(principal, db)
    assert user.role == 'viewer'
    with pytest.raises(HTTPException) as caught:
        ensure_course_access(user, 'course-b')
    assert caught.value.status_code == 403
    with pytest.raises(HTTPException):
        require_permission('manage_settings')(user, db)


@pytest.mark.parametrize('scope_type', ['CAMPUS', 'SYSTEM'])
def test_all_campus_owner_manages_catalog_and_only_delegates_individual_campuses(db, scope_type):
    own = grant(db, scope_type=scope_type)
    user = actor(db)
    service = BusinessRBACService(db)
    assert _require_academic_catalog_admin(user, db) is user
    assert service.has_any_business_permission(user, 'view_rbac')
    for permission in ['manage_settings', 'bank.view', 'question.generate', 'quiz.create_openedx', 'user.manage_all']:
        assert not service.has_any_business_permission(user, permission)
    child = service.create_assignment(actor=user, user_id='campus-lead', email=None, role_code='CAMPUS_OWNER', scope_type='CAMPUS', scope_id='hn')
    rows = list_assignments(user=user, db=db)['items']
    assert {row['id']: row['can_revoke'] for row in rows} == {own.id: False, child.id: True}
    assert service.revoke_assignment(child.id, user).revoked_at is not None
    for role, target_type, target_id in [('SYSTEM_ADMIN', 'SYSTEM', '*'), ('CAMPUS_OWNER', 'CAMPUS', '*'), ('CAMPUS_OWNER', 'SYSTEM', '*')]:
        with pytest.raises(HTTPException) as caught:
            service.create_assignment(actor=user, user_id='other', email=None, role_code=role, scope_type=target_type, scope_id=target_id)
        assert caught.value.status_code == 403
    assert not service.can_grant(user, 'SUBJECT_OWNER', 'SUBJECT', 'any-subject')
    assert not service.can_grant(user, 'DEPARTMENT_HEAD', 'DEPARTMENT', 'any-department')
    with pytest.raises(HTTPException):
        service.revoke_assignment(own.id, user)


def test_individual_campus_owner_cannot_manage_global_catalog_or_delegate(db):
    grant(db, scope_id='hn')
    user = actor(db)
    service = BusinessRBACService(db)
    assert service.has_any_business_permission(user, 'academic.manage_campus')
    assert not service.can_grant(user, 'CAMPUS_OWNER', 'CAMPUS', 'hn')
    with pytest.raises(HTTPException) as caught:
        _require_academic_catalog_admin(user, db)
    assert caught.value.status_code == 403


def test_staff_claim_alone_does_not_become_system_admin(db):
    user = get_user_context(Principal(user_id='staff', role='viewer', raw_claims={'is_staff': True}), db)
    assert user.role == 'viewer'
    assert not BusinessRBACService(db).is_system_admin(user)


@pytest.mark.parametrize('proof,allowed', [({'is_staff': True}, False), ({'is_superuser': True}, True), ({'ai_system_admin': True}, True)])
def test_admin_tokens_still_require_trusted_proof(db, monkeypatch, proof, allowed):
    monkeypatch.setattr(settings, 'jwt_secret', 'test-only-key-for-admin-proof-regression')
    monkeypatch.setattr(security, 'is_session_revoked', lambda _jti: False)
    token = security.jwt.encode({
        'sub': 'token-user', 'role': 'admin', 'token_type': 'ai_session',
        'exp': int(time.time()) + 60, 'iss': settings.jwt_issuer,
        'aud': settings.jwt_audience, **proof,
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    if allowed:
        user = get_user_context(security._principal_from_jwt(token), db)
        assert user.role == 'admin'
        assert require_permission('future.permission')(user, db) is user
    else:
        with pytest.raises(HTTPException) as caught:
            security._principal_from_jwt(token)
        assert caught.value.status_code == 403


def test_all_campus_owner_can_save_read_and_retire_semester_through_http(db):
    grant(db)
    app = FastAPI()
    app.include_router(academic_router, prefix='/academic')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_principal] = lambda: Principal(user_id='owner', role='viewer')
    with TestClient(app) as client:
        response = client.post('/academic/terms', json={'term_code': 'FA26', 'term_name': 'Fall 2026', 'branch': 'poly', 'blocks': []})
        assert response.status_code == 200, response.text
        term_id = response.json()['id']
        assert client.get(f'/academic/terms/{term_id}/with-blocks').status_code == 200
        assert client.delete(f'/academic/terms/{term_id}').status_code == 200
        row = db.query(UserRoleAssignment).filter_by(user_id='owner').one()
        row.scope_id = 'hn'
        db.commit()
        assert client.post('/academic/terms', json={'term_code': 'SP27', 'term_name': 'Spring 2027', 'branch': 'poly'}).status_code == 403


def worker_actor(user):
    from app.api.routes.academic import _requester_context_json
    from app.worker import _worker_user_from_request_json
    snapshot = _requester_context_json(user)
    return _worker_user_from_request_json({'requester_context': snapshot}, fallback_user_id=user.user_id, source='test', job_id='sync-1'), snapshot


@pytest.mark.parametrize('claim', ['is_superuser', 'is_super_admin', 'ai_system_admin'])
def test_cms_admin_remains_authorized_in_grade_sync_worker(db, claim):
    from app.services.academic.access import AcademicAccessWorkflowService
    user = get_user_context(Principal(user_id='29', role='admin', raw_claims={claim: True, 'token': 'do-not-copy'}), db)
    worker, snapshot = worker_actor(user)
    assert 'token' not in str(snapshot)
    assert snapshot['authenticated_admin_claims'] == {claim: True}
    AcademicAccessWorkflowService(db, BusinessRBACService(db)).assert_can_access_class(worker, 'any-class')


@pytest.mark.parametrize('claims', [{}, {'is_staff': True}, {'ai_system_admin': 'true'}])
def test_grade_sync_worker_does_not_trust_admin_label_or_staff(db, claims):
    from app.core.rbac import UserContext
    from app.services.academic.access import AcademicAccessWorkflowService
    worker, _ = worker_actor(UserContext(user_id='unassigned', role='admin', permissions=set(), raw_claims=claims))
    with pytest.raises(HTTPException) as caught:
        AcademicAccessWorkflowService(db, BusinessRBACService(db)).assert_can_access_class(worker, 'any-class')
    assert caught.value.status_code == 403


def test_queued_database_admin_grant_is_rechecked_after_revocation(db):
    from app.services.academic.access import AcademicAccessWorkflowService
    row = grant(db, role='SYSTEM_ADMIN', scope_type='SYSTEM', scope_id='*')
    worker, snapshot = worker_actor(actor(db))
    assert snapshot['authenticated_admin_claims'] == {}
    access = AcademicAccessWorkflowService(db, BusinessRBACService(db))
    access.assert_can_access_class(worker, 'any-class')
    row.revoked_at = datetime.utcnow()
    db.commit()
    with pytest.raises(HTTPException):
        access.assert_can_access_class(worker, 'any-class')
