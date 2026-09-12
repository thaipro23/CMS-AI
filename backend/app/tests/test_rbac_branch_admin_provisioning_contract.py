from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.rbac import get_user_context
from app.core.security import Principal
from app.db.session import Base
from app.models import cost, job, question  # noqa: F401
from app.models.academic import AcademicCampus
from app.models.rbac import UserRoleAssignment
from app.services.business_rbac import BusinessRBACService
ROOT = Path(__file__).resolve().parents[3]

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(settings, 'app_env', 'production')
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        BusinessRBACService(session).ensure_default_catalog()
        session.add_all([AcademicCampus(campus_code='hn', campus_name='Hà Nội', branch='poly'), AcademicCampus(campus_code='hp', campus_name='Hải Phòng', branch='poly'), AcademicCampus(campus_code='ct', campus_name='Cần Thơ', branch='ptcd')])
        session.commit()
        yield session
    engine.dispose()

def actor(db: Session, user_id: str):
    return get_user_context(Principal(user_id=user_id, role='viewer', raw_claims={'username': user_id}), db)

def grant(db: Session, user_id: str, scope_type: str, scope_id: str):
    item = UserRoleAssignment(user_id=user_id, role_code='CAMPUS_OWNER', scope_type=scope_type, scope_id=scope_id)
    db.add(item); db.commit(); return item

def test_branch_admin_delegates_only_own_branch_and_campus_admin_cannot_delegate(db):
    grant(db, 'poly-admin', 'BRANCH', 'poly'); grant(db, 'campus-admin', 'CAMPUS', 'hn')
    service = BusinessRBACService(db)
    poly = actor(db, 'poly-admin')
    assert service.has_any_business_permission(poly, 'view_rbac')
    assert service.can_grant(poly, 'CAMPUS_OWNER', 'CAMPUS', 'hn')
    assert service.can_grant(poly, 'CAMPUS_OWNER', 'CAMPUS', 'hp')
    assert not service.can_grant(poly, 'CAMPUS_OWNER', 'CAMPUS', 'ct')
    assert not service.can_grant(poly, 'CAMPUS_OWNER', 'BRANCH', 'poly')
    campus = actor(db, 'campus-admin')
    assert not service.has_any_business_permission(campus, 'view_rbac')
    assert not service.can_grant(campus, 'CAMPUS_OWNER', 'CAMPUS', 'hn')

def test_email_provisioning_precedes_assignment_and_returns_metadata(db, monkeypatch):
    root = get_user_context(Principal(user_id='root', role='admin', raw_claims={'is_superuser': True}), db)
    calls = []
    def fake(*, username: str, email: str, require_staff: bool = False):
        calls.append((username, email, require_staff))
        return {'status': 'created', 'username': username, 'email': email, 'openedx_user_id': 123, 'profile_ok': True, 'password_policy': 'unusable_password', 'is_staff': require_staff, 'is_superuser': False}
    monkeypatch.setattr(BusinessRBACService, '_provision_cms_identity', staticmethod(fake))
    items, created, reused = BusinessRBACService(db).create_assignments_batch(actor=root, user_id='wrong', email='New.Admin@fpt.edu.vn', role_code='CAMPUS_OWNER', scope_type='BRANCH', scope_ids=['poly'])
    assert calls == [('new.admin', 'new.admin@fpt.edu.vn', True)]
    assert (created, reused) == (1, 0)
    assert items[0].user_id == 'new.admin'
    assert items[0].metadata_json['cms_provisioning']['status'] == 'created'
    assert items[0].metadata_json['cms_provisioning']['is_staff'] is True
    assert items[0].metadata_json['cms_provisioning']['is_superuser'] is False

def test_failed_provisioning_creates_no_assignment(db, monkeypatch):
    root = get_user_context(Principal(user_id='root', role='admin', raw_claims={'is_superuser': True}), db)
    def fail(**_kwargs): raise RuntimeError('connector failed')
    monkeypatch.setattr(BusinessRBACService, '_provision_cms_identity', staticmethod(fail))
    with pytest.raises(RuntimeError):
        BusinessRBACService(db).create_assignments_batch(actor=root, user_id='ignored', email='fail.user@fpt.edu.vn', role_code='CAMPUS_OWNER', scope_type='BRANCH', scope_ids=['ptcd'])
    assert db.query(UserRoleAssignment).filter_by(user_id='fail.user').count() == 0

def test_campus_owner_without_email_is_rejected_before_assignment(db):
    root = get_user_context(Principal(user_id='root', role='admin', raw_claims={'is_superuser': True}), db)
    with pytest.raises(Exception, match='email'):
        BusinessRBACService(db).create_assignments_batch(
            actor=root,
            user_id='campus.owner',
            email=None,
            role_code='CAMPUS_OWNER',
            scope_type='BRANCH',
            scope_ids=['poly'],
        )
    assert db.query(UserRoleAssignment).filter_by(user_id='campus.owner').count() == 0

def test_users_ui_contract():
    page = (ROOT / 'frontend/app/users/page.tsx').read_text(encoding='utf-8')
    for marker in ['Admin Poly', 'Admin PTCĐ', 'Admin cơ sở', 'canLoadPolyCampuses', 'canLoadPtcdCampuses', 'cms_provisioning', 'Đã tạo tài khoản CMS', 'Tài khoản CMS đã tồn tại', 'Đã xác nhận quyền CMS staff', 'branch: campus.branch']:
        assert marker in page
    assert 'Tài khoản Open edX' not in page
    assert "form.role_code === 'CAMPUS_OWNER' ? 'campus_owner.assign'" in page
