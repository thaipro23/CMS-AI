from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.api.routes import academic  # noqa: F401
from app.models import cost, job, question  # noqa: F401
from app.models.academic import AcademicCampus, AcademicTerm
from app.models.rbac import UserRoleAssignment
from app.schemas.rbac import RoleAssignmentCreate
from app.services.business_rbac import BusinessRBACService


@pytest.fixture
def scope_db():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        BusinessRBACService(db).ensure_default_catalog()
        db.add_all([
            AcademicCampus(campus_code='hn', campus_name='Poly HN', branch='poly'),
            AcademicCampus(campus_code='dn', campus_name='PTCD DN', branch='ptcd'),
            AcademicCampus(campus_code='shared', campus_name='Poly shared', branch='poly'),
            AcademicCampus(campus_code='shared', campus_name='PTCD shared', branch='ptcd'),
            AcademicCampus(campus_code='unknown', campus_name='Unclassified', branch=None),
            AcademicTerm(id='poly-term', term_code='P', term_name='Poly', branch='poly'),
            AcademicTerm(id='ptcd-term', term_code='T', term_name='PTCD', branch='ptcd'),
        ])
        db.commit()
        yield db
    engine.dispose()


def grant(db, scope_type='BRANCH', scope_id='poly'):
    user = SimpleNamespace(user_id='owner', role='viewer', raw_claims={})
    db.add(UserRoleAssignment(user_id=user.user_id, role_code='CAMPUS_OWNER', scope_type=scope_type, scope_id=scope_id))
    db.commit()
    return user, BusinessRBACService(db)


def test_branch_owner_has_finite_branch_campuses_and_catalog_permissions(scope_db):
    user, service = grant(scope_db)
    assert service.accessible_branch_codes(user) == {'poly'}
    assert service.accessible_campus_codes(user) == {'hn', 'shared'}
    assert service.has_any_business_permission(user, 'academic.catalog.manage')
    assert service.has_permission(user, 'academic.catalog.manage', service.entity_scope('BRANCH', 'poly'))
    assert not service.has_permission(user, 'academic.catalog.manage', service.entity_scope('BRANCH', 'ptcd'))
    assert not service.has_permission(user, 'academic.catalog.manage', service.entity_scope('SYSTEM', '*'))


def test_branch_owner_delegates_only_unambiguous_same_branch_campus(scope_db):
    user, service = grant(scope_db)
    assert service.can_grant(user, 'CAMPUS_OWNER', 'CAMPUS', 'hn')
    assert not service.can_grant(user, 'CAMPUS_OWNER', 'CAMPUS', 'dn')
    assert not service.can_grant(user, 'CAMPUS_OWNER', 'CAMPUS', 'shared')
    assert not service.can_grant(user, 'CAMPUS_OWNER', 'BRANCH', 'poly')
    assert not service.can_grant(user, 'CAMPUS_OWNER', 'SYSTEM', '*')


def test_legacy_wildcard_fails_closed_pending_explicit_reassignment(scope_db):
    user, service = grant(scope_db, 'CAMPUS', '*')
    assert service.accessible_campus_codes(user) == set()
    assert service.accessible_branch_codes(user) == set()
    assert not service.has_any_business_permission(user, 'academic.catalog.manage')
    assert not service.has_permission(user, 'academic.manage_campus', service.entity_scope('CAMPUS', 'dn'))
    with pytest.raises(HTTPException):
        service._validate_assignment_scope('CAMPUS_OWNER', 'CAMPUS', '*')


def test_only_system_scope_owner_is_unrestricted(scope_db):
    user, service = grant(scope_db, 'SYSTEM', '*')
    assert service.accessible_branch_codes(user) is None
    assert service.accessible_campus_codes(user) is None
    assert service.can_grant(user, 'CAMPUS_OWNER', 'CAMPUS', 'dn')


def test_branch_filter_checks_explicit_branch_and_term(scope_db):
    user, service = grant(scope_db)
    service.ensure_requested_branch_filter_allowed(user, 'poly', term_id='poly-term')
    service.ensure_requested_branch_filter_allowed(user, None, term_id='poly-term', require_filter_when_scoped=True)
    for branch, term in [('ptcd', None), (None, 'ptcd-term'), ('poly', 'ptcd-term')]:
        with pytest.raises(HTTPException) as caught:
            service.ensure_requested_branch_filter_allowed(user, branch, term_id=term)
        assert caught.value.status_code == 403
    with pytest.raises(HTTPException):
        service.ensure_requested_branch_filter_allowed(user, None, require_filter_when_scoped=True)


def test_branch_assignment_schema_and_validation(scope_db):
    payload = RoleAssignmentCreate(user_id='owner', role_code='CAMPUS_OWNER', scope_type='branch', scope_id='poly')
    assert payload.scope_type == 'BRANCH'
    service = BusinessRBACService(scope_db)
    service._validate_assignment_scope('CAMPUS_OWNER', 'BRANCH', 'poly')
    for branch in ['*', '', 'other']:
        with pytest.raises(HTTPException):
            service._validate_assignment_scope('CAMPUS_OWNER', 'BRANCH', branch)
    assert 'Poly' in service.scope_label('BRANCH', 'poly')


def test_unique_campus_scope_resolves_its_branch_and_ambiguous_scope_does_not(scope_db):
    user, service = grant(scope_db, 'CAMPUS', 'hn')
    assert service.accessible_branch_codes(user) == {'poly'}
    scope_db.query(UserRoleAssignment).update({'scope_id': 'shared'})
    scope_db.commit()
    assert service.accessible_branch_codes(user) == set()
    assert service.accessible_campus_codes(user) == set()
