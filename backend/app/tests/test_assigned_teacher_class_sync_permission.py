from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import academic as academic_routes
from app.api.routes.academic import _require_academic_class_sync_permission
from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicCampus,
    AcademicClass,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.models.rbac import RBACPermission, RBACRole, RBACRolePermission, UserRoleAssignment
from app.services.academic_service import AcademicService
from app.services.business_rbac import BusinessRBACService
from app.schemas.academic import AcademicFullCmsSyncIn


def _teacher_user() -> UserContext:
    return UserContext(
        user_id='teacher-01',
        username='teacher-01',
        email='teacher-01@example.test',
        role='viewer',
        permissions={'academic.view', 'view_training_reports'},
        raw_claims={'username': 'teacher-01'},
    )


def _create_schema(engine) -> None:
    for model in (
        RBACRole,
        RBACPermission,
        RBACRolePermission,
        UserRoleAssignment,
        AcademicCampus,
        AcademicTerm,
        AcademicBlock,
        AcademicSubject,
        AcademicClass,
        AcademicTeacher,
        AcademicTeacherAssignment,
    ):
        model.__table__.create(engine)


def _seed_teacher_scope(db: Session) -> None:
    term = AcademicTerm(
        id='term-fa26',
        term_code='FA26',
        term_name='Fall 2026',
        branch='poly',
        active=True,
    )
    block = AcademicBlock(
        id='block-1',
        term_id=term.id,
        block_code='B1',
        block_name='Block 1',
        active=True,
    )
    subject = AcademicSubject(
        id='subject-1',
        subject_code='SOA102',
        subject_name='Service Oriented Architecture',
        branch='poly',
        active=True,
    )
    assigned = AcademicClass(
        id='class-assigned',
        term_id=term.id,
        block_id=block.id,
        subject_id=subject.id,
        class_code='SOA102.01',
        class_name='SOA102.01',
        campus='hn',
        branch='poly',
        active=True,
    )
    other = AcademicClass(
        id='class-other',
        term_id=term.id,
        block_id=block.id,
        subject_id=subject.id,
        class_code='SOA102.02',
        class_name='SOA102.02',
        campus='hn',
        branch='poly',
        active=True,
    )
    teacher = AcademicTeacher(
        id='teacher-row-1',
        username='teacher-01',
        email='teacher-01@example.test',
        full_name='Teacher One',
        campus='hn',
        branch='poly',
        active=True,
    )
    db.add_all([
        term,
        block,
        subject,
        assigned,
        other,
        teacher,
        AcademicTeacherAssignment(
            id='assignment-1',
            teacher_id=teacher.id,
            class_id=assigned.id,
            subject_id=subject.id,
            term_id=term.id,
            block_id=block.id,
            campus='hn',
            branch='poly',
            source='ap',
        ),
    ])
    db.commit()


def test_ap_assigned_teacher_can_enter_class_sync_route_but_not_another_class():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    _create_schema(engine)
    with Session(engine) as db:
        BusinessRBACService(db).ensure_default_catalog()
        _seed_teacher_scope(db)
        user = _teacher_user()

        assert _require_academic_class_sync_permission(user, db) is user
        AcademicService(db).assert_can_access_class(user, 'class-assigned')
        with pytest.raises(HTTPException) as caught:
            AcademicService(db).assert_can_access_class(user, 'class-other')

        assert caught.value.status_code == 403
    engine.dispose()


def test_assigned_teacher_role_exposes_only_the_dedicated_sync_permission():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    _create_schema(engine)
    with Session(engine) as db:
        BusinessRBACService(db).ensure_default_catalog()
        _seed_teacher_scope(db)
        permissions = BusinessRBACService(db).effective_permissions_for_user(_teacher_user())

        assert 'academic.sync_assigned_class' in permissions
        assert 'academic.manage_campus' not in permissions
        assert 'academic.catalog.manage' not in permissions
    engine.dispose()


def test_full_cms_endpoint_never_combines_learning_score_refresh(monkeypatch):
    captured = {}

    def fake_enqueue(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(academic_routes, '_enqueue_class_sync_job', fake_enqueue)
    academic_routes.enqueue_class_full_cms_sync(
        'class-assigned',
        AcademicFullCmsSyncIn(
            force=True,
            limit=500,
            auto_map_course=True,
            sync_learning=True,
        ),
        user=_teacher_user(),
        db=object(),
    )

    assert captured['job_type'] == 'full_cms_sync'
    assert captured['force'] is False
    assert captured['auto_map_course'] is True
    assert captured['sync_learning'] is False
