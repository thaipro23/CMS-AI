from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.api.routes import academic  # noqa: F401
from app.models import cost, job, question  # noqa: F401
from app.models.academic import AcademicCampus, AcademicSubject, AcademicSyncRun, AcademicTerm
from app.models.rbac import UserRoleAssignment
from app.schemas.academic import AcademicAPSyncIn, AcademicCampusUpsertIn, AcademicImportFromJsonIn
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



def test_branch_owner_academic_routes_fail_closed_across_poly_ptcd(scope_db):
    user, _service = grant(scope_db)
    scope_db.add_all([
        AcademicSubject(id='poly-subject', subject_code='POLY101', subject_name='Poly subject', branch='poly'),
        AcademicSubject(id='ptcd-subject', subject_code='PTCD101', subject_name='PTCD subject', branch='ptcd'),
        AcademicSyncRun(id='poly-run', source='ap', mode='api_all', status='completed', requested_by='owner', term_name='Poly', branch='poly'),
        AcademicSyncRun(id='ptcd-run', source='ap', mode='api_all', status='completed', requested_by='other', term_name='PTCD', branch='ptcd'),
    ])
    scope_db.commit()

    # Omitted branch filters must still return only the actor's branch.
    subjects = academic.list_subjects(
        term_id=None,
        block_id=None,
        search=None,
        branch=None,
        user=user,
        db=scope_db,
    )
    assert [item.subject_code for item in subjects] == ['POLY101']

    jobs = academic.list_ap_sync_jobs(
        term_name='',
        branch='',
        status_filter='all',
        limit=10,
        user=user,
        db=scope_db,
    )
    assert [item.id for item in jobs] == ['poly-run']

    # Explicit cross-branch reads and writes are rejected before any catalog/AP work.
    forbidden_calls = [
        lambda: academic.list_subjects(
            term_id=None,
            block_id=None,
            search=None,
            branch='ptcd',
            user=user,
            db=scope_db,
        ),
        lambda: academic.get_term_with_blocks(
            term_id='ptcd-term',
            active_blocks=None,
            user=user,
            db=scope_db,
        ),
        lambda: academic.get_ap_sync_options(
            term_name='',
            branch='ptcd',
            campus=None,
            include_subjects=False,
            user=user,
            db=scope_db,
        ),
        lambda: academic.get_ap_sync_job(
            run_id='ptcd-run',
            user=user,
            db=scope_db,
        ),
        lambda: academic.upsert_academic_campus(
            payload=AcademicCampusUpsertIn(campus_code='new-ptcd', campus_name='PTCD', branch='ptcd'),
            user=user,
            db=scope_db,
        ),
        lambda: academic.enqueue_sync_from_ap_job(
            payload=AcademicAPSyncIn(term_name='PTCD', sync_scope='campus', campuses=['dn'], branch='ptcd'),
            user=user,
            db=scope_db,
        ),
        lambda: academic.sync_from_json(
            payload=AcademicImportFromJsonIn(payload={}, campus='dn', branch='ptcd'),
            user=user,
            db=scope_db,
        ),
    ]
    for call in forbidden_calls:
        with pytest.raises(HTTPException) as caught:
            call()
        assert caught.value.status_code == 403

    ptcd_campus = scope_db.query(AcademicCampus).filter(
        AcademicCampus.campus_code == 'dn',
        AcademicCampus.branch == 'ptcd',
    ).one()
    with pytest.raises(HTTPException) as caught:
        academic.delete_academic_campus(campus_id=ptcd_campus.id, user=user, db=scope_db)
    assert caught.value.status_code == 403


def test_branch_admin_frontend_uses_rbac_branch_choices():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    context = (root / 'frontend/context/AppContext.tsx').read_text(encoding='utf-8')
    assert "academicBranches: Array<'poly' | 'ptcd'>" in context
    assert "scope_type || '').toUpperCase() === 'BRANCH'" in context

    scoped_pages = [
        'frontend/app/student-management/StudentManagementPlatformPage.tsx',
        'frontend/app/teacher-management/TeacherManagementPlatformPage.tsx',
        'frontend/app/subject-management/page.tsx',
        'frontend/app/analytics/learning/page.tsx',
        'frontend/app/premises/page.tsx',
        'frontend/app/semesters/page.tsx',
        'frontend/app/ap-sync/page.tsx',
    ]
    for relative in scoped_pages:
        source = (root / relative).read_text(encoding='utf-8')
        assert 'academicBranches' in source, relative

    ap_sync = (root / 'frontend/app/ap-sync/page.tsx').read_text(encoding='utf-8')
    assert 'availableBranches.map' in ap_sync
    assert "requestRunForBranches(['poly', 'ptcd'])" not in ap_sync
